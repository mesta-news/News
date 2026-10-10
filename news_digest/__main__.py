"""Build the daily digest.

    python -m news_digest                 # full run
    python -m news_digest --no-ai         # skip Claude summaries
    python -m news_digest --render-only   # re-render the site from data/*.json
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from . import markets, pages, sources, summarize
from .notify import send_email

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Amsterdam")
SITE_DAYS = 90  # how many past digests the archive page links to

log = logging.getLogger("news_digest")


# --------------------------------------------------------------------------- state

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))


# --------------------------------------------------------------------------- build

def build(cfg: dict, state_dir: Path, use_ai: bool) -> dict:
    now = datetime.now(timezone.utc)
    today = now.astimezone(TZ).date().isoformat()

    seen_path, pages_path = state_dir / "seen.json", state_dir / "pages.json"
    seen: dict[str, str] = load_json(seen_path, {})
    page_state: dict = load_json(pages_path, {})
    watchlist = cfg.get("watchlist") or []

    def build_section(sec: dict) -> dict:
        items, errors = sources.collect(sec, watchlist, now)
        for it in items:
            first = seen.setdefault(it.id, today)
            it.is_new = first == today  # re-running on the same day keeps items "new"
        return {
            "id": sec["id"], "title": sec["title"], "icon": sec.get("icon", ""),
            "max_items": sec.get("max_items", 15),
            "items": [i.to_dict() for i in items[: sec.get("max_items", 15) + 30]],
            "errors": errors,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        sections = list(pool.map(build_section, cfg["sections"]))

    for sec_cfg, sec in zip(cfg["sections"], sections):
        # Keep the top new articles plus already-shown ones for the "earlier" list.
        sec["items"] = [i for i in sec["items"] if i["is_new"]][: sec["max_items"]] + \
            [i for i in sec["items"] if not i["is_new"]]
        sec["pages"] = pages.check(sec_cfg.get("watch_pages") or [], page_state, today)
        if sec["id"] == "watchlist":
            sec["quotes"], err = markets.quotes(watchlist, now.astimezone(TZ))
            if err:
                sec["errors"].append(err)
        sec["new_count"] = sum(1 for i in sec["items"] if i["is_new"])

    client = summarize._client() if use_ai else None
    top: list[str] = []
    if client:
        with ThreadPoolExecutor(max_workers=5) as pool:
            briefings = list(pool.map(
                lambda s: summarize.section_briefing(client, cfg, s), sections))
        for sec, brief in zip(sections, briefings):
            sec["briefing"] = brief
            if not brief:
                sec["errors"].append("AI summary failed for this section (see workflow log).")
                continue
            notes = {h["id"]: h["note"] for h in brief["highlights"]}
            for it in sec["items"]:
                it["note"] = notes.get(it["id"], "")
            # Put the highlighted articles first (sort is stable, so ranking is kept).
            sec["items"].sort(key=lambda i: not i["note"])
        top = summarize.top_briefing(client, cfg, sections)
    elif use_ai:
        log.info("ANTHROPIC_API_KEY not set - skipping AI summaries")

    # Forget old "seen" ids so the state file stays small.
    keep_after = (now - timedelta(days=cfg.get("seen_retention_days", 60))).date().isoformat()
    seen = {k: v for k, v in seen.items() if v >= keep_after}
    save_json(seen_path, seen)
    save_json(pages_path, page_state)

    local = now.astimezone(TZ)
    return {
        "date": today,
        "date_label": local.strftime("%A %d %B %Y"),
        "generated_label": local.strftime("%H:%M %Z"),
        "ai": bool(client),
        "top": top,
        "sections": sections,
    }


# --------------------------------------------------------------------------- render

def _markdown(text: str) -> Markup:
    # Escape first: the text is model output derived from untrusted web content.
    return Markup(md.markdown(html.escape(text or "", quote=False)))


def _sparkline(values: list[float] | None, w: int = 90, h: int = 22) -> Markup:
    if not values or len(values) < 2:
        return Markup("")
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = w / (len(values) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}"
                   for i, v in enumerate(values))
    color = "var(--up)" if values[-1] >= values[0] else "var(--down)"
    return Markup(f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                  f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"/></svg>')


def jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters["md"] = _markdown
    env.filters["spark"] = _sparkline
    return env


def render_site(data_dir: Path, out_dir: Path) -> str:
    """Render index.html, one page per day and archive.html. Returns index HTML."""
    env = jinja_env()
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(data_dir.glob("*.json"), reverse=True)[:SITE_DAYS]
    entries, index_html = [], ""
    page = env.get_template("digest.html.j2")
    for f in files:
        d = load_json(f, None)
        if not d:
            continue
        out = page.render(d=d)
        (out_dir / f"{d['date']}.html").write_text(out)
        if not index_html:
            index_html = out
        entries.append({"date": d["date"], "label": d["date_label"],
                        "new_count": sum(s.get("new_count", 0) for s in d["sections"])})
    (out_dir / "index.html").write_text(index_html or "<p>No digest yet.</p>")
    (out_dir / "archive.html").write_text(
        env.get_template("archive.html.j2").render(entries=entries))
    return index_html


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=ROOT / "config.yaml", type=Path)
    ap.add_argument("--data", default=ROOT / "data", type=Path, help="daily JSON snapshots")
    ap.add_argument("--state", default=ROOT / "state", type=Path, help="seen articles / watched pages")
    ap.add_argument("--out", default=ROOT / "_site", type=Path, help="rendered website")
    ap.add_argument("--no-ai", action="store_true", help="skip Claude summaries")
    ap.add_argument("--render-only", action="store_true", help="only re-render from --data")
    ap.add_argument("--email", action="store_true", help="email the digest (needs SMTP_* env vars)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not args.render_only:
        cfg = yaml.safe_load(args.config.read_text())
        digest = build(cfg, args.state, use_ai=not args.no_ai)
        save_json(args.data / f"{digest['date']}.json", digest)
        log.info("digest %s: %d new articles", digest["date"],
                 sum(s["new_count"] for s in digest["sections"]))
    index_html = render_site(args.data, args.out)
    if args.email:
        send_email(index_html, os.environ.get("DIGEST_URL", ""))


if __name__ == "__main__":
    main()
