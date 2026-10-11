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
import re
import shutil
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from . import alerts, articles, curve, icons, lock, markets, pages, push, rates, sources, summarize, weather
from .notify import send_email

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Amsterdam")
SITE_DAYS = 90  # how many past digests the archive page links to

log = logging.getLogger("news_digest")


# --------------------------------------------------------------------------- state

# With SITE_PASSPHRASE set, saved editions and state are stored encrypted, so the
# public repo holds only ciphertext. Plain files from before still load.

def load_json(path: Path, default):
    try:
        text = path.read_text()
        data = json.loads(text)
    except (FileNotFoundError, json.JSONDecodeError):
        return default
    if isinstance(data, dict) and data.get("locked") == 1 and set(data) == {"locked", "iv", "ct"}:
        if not lock.passphrase():
            raise SystemExit(f"{path} is encrypted: set SITE_PASSPHRASE to read it")
        return json.loads(lock.unlock_json(text, lock.passphrase()))
    return data


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
    secret = lock.passphrase()
    path.write_text(lock.lock_json(text, secret) if secret else text)


def encrypt_stored(*dirs: Path) -> None:
    """Re-save plain JSON files encrypted (once, after SITE_PASSPHRASE is added)."""
    if not lock.passphrase():
        return
    count = 0
    for folder in dirs:
        for f in folder.glob("*.json"):
            raw = json.loads(f.read_text())
            if not (isinstance(raw, dict) and raw.get("locked") == 1):
                save_json(f, raw)
                count += 1
    if count:
        log.info("encrypted %d stored file(s)", count)


# --------------------------------------------------------------------------- build

def _balance(items: list[dict], groups: list[str] | None) -> list[dict]:
    """Interleave ranked items by group so one busy group can't crowd out the others."""
    if not groups:
        return items
    queues = {g: [i for i in items if i.get("group") == g] for g in groups}
    rest = [i for i in items if i.get("group") not in queues]
    out = []
    while any(queues.values()):
        for g in groups:
            if queues[g]:
                out.append(queues[g].pop(0))
    return out + rest


def _editions(data_dir: Path | None, before: str, days: int) -> list[dict]:
    """Saved editions dated before `before`, newest first (at most `days` of them)."""
    if not data_dir:
        return []
    out = []
    for f in sorted(data_dir.glob("*.json"), reverse=True):
        if f.stem < before and len(out) < days:
            d = load_json(f, None)
            if d:
                out.append(d)
    return out


def _previous_summaries(previous: dict | None) -> dict[str, str]:
    """Each section's briefing from the last earlier edition, so Claude can follow up."""
    return {s["id"]: s["briefing"]["summary"] for s in (previous or {}).get("sections", [])
            if (s.get("briefing") or {}).get("summary")}


def _previous_rates(previous: dict | None) -> dict[str, dict[str, float]]:
    """section id -> {rate name: value} from the last edition, for change alerts."""
    return {s["id"]: {r["name"]: r["value"] for r in s.get("rates") or [] if r.get("value") is not None}
            for s in (previous or {}).get("sections", [])}


def build(cfg: dict, state_dir: Path, use_ai: bool, data_dir: Path | None = None) -> dict:
    now = datetime.now(timezone.utc)
    today = now.astimezone(TZ).date().isoformat()

    seen_path, pages_path = state_dir / "seen.json", state_dir / "pages.json"
    history = _editions(data_dir, today, 7)  # the past week, newest first
    previous = history[0] if history else None
    seen: dict[str, str] = load_json(seen_path, {})
    page_state: dict = load_json(pages_path, {})
    watchlist = cfg.get("watchlist") or []

    def instruments(sec: dict) -> list[dict]:
        """Price tiles of a section: its own `quotes:` list, or the global watchlist."""
        return sec.get("quotes") or (watchlist if sec["id"] == "watchlist" else [])

    def build_section(sec: dict) -> dict:
        items, errors = sources.collect(sec, instruments(sec), now)
        for it in items:
            first = seen.setdefault(it.id, today)
            it.is_new = first == today  # re-running on the same day keeps items "new"
        return {
            "id": sec["id"], "title": sec["title"], "short": sec.get("short", ""),
            "emoji": sec.get("emoji", ""), "color": sec.get("color"),
            "max_items": sec.get("max_items", 15),
            "items": [i.to_dict() for i in items[: sec.get("max_items", 15) + 30]],
            "errors": errors,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        sections = list(pool.map(build_section, cfg["sections"]))

    for sec_cfg, sec in zip(cfg["sections"], sections):
        # Keep the top new articles plus already-shown ones for the "earlier" list.
        fresh = _balance([i for i in sec["items"] if i["is_new"]], sec_cfg.get("groups"))
        sec["items"] = fresh[: sec["max_items"]] + [i for i in sec["items"] if not i["is_new"]]
        if sec_cfg.get("groups"):
            sec["groups"] = sec_cfg["groups"]
        if sec_cfg.get("rates_label"):
            sec["rates_label"] = sec_cfg["rates_label"]
        sec["pages"] = pages.check(sec_cfg.get("watch_pages") or [], page_state, today)
        sec["alerts"] = []
        if instruments(sec_cfg):
            sec["quotes"], err = markets.quotes(instruments(sec_cfg), now.astimezone(TZ))
            if err:
                sec["errors"].append(err)
            sec["alerts"] += alerts.market_alerts(sec["quotes"], instruments(sec_cfg))
        # Rate tiles: a section's own `rates:` list, or the global one for the rates tab.
        rate_defs = sec_cfg.get("rates") or (cfg.get("rates") if sec["id"] == "rates" else None)
        if rate_defs:
            sec["rates"], err = rates.fetch(rate_defs)
            if err:
                sec["errors"].append(err)
            sec["alerts"] += alerts.rate_alerts(sec["rates"], rate_defs,
                                                _previous_rates(previous).get(sec["id"], {}))
        if sec_cfg.get("yield_curve"):
            sec["curve"] = curve.fetch()
        sec["new_count"] = sum(1 for i in sec["items"] if i["is_new"])

    earlier = _previous_summaries(previous)
    for sec in sections:
        if sec["id"] in earlier:
            sec["previous_briefing"] = earlier[sec["id"]]

    client = summarize._client() if use_ai else None
    if client:
        articles.enrich(sections)  # article text for Claude's reader summaries, plus images
    top: list[str] = []
    if client:
        with ThreadPoolExecutor(max_workers=3) as pool:
            briefings = list(pool.map(
                lambda s: summarize.section_briefing(client, cfg, s), sections))
        for sec, brief in zip(sections, briefings):
            sec["briefing"] = brief
            if not brief:
                sec["errors"].append("AI summary failed for this section (see workflow log).")
                continue
            notes = {h["id"]: h["note"] for h in brief["highlights"]}
            summaries = {a["id"]: a["summary"] for a in brief.get("article_summaries") or []}
            brief.pop("article_summaries", None)  # stored on the items instead
            for it in sec["items"]:
                it["note"] = notes.get(it["id"], "")
                if summaries.get(it["id"]):
                    it["summary"] = summaries[it["id"]]
            # Put the highlighted articles first (sort is stable, so ranking is kept).
            sec["items"].sort(key=lambda i: not i["note"])
            alert = brief.get("alert") or {}
            if alert.get("important") and alert.get("headline"):
                sec["alerts"].insert(0, alert["headline"])
        top = summarize.top_briefing(client, cfg, sections)
    elif use_ai:
        log.info("No CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY - skipping AI summaries")

    for sec in sections:
        sec.pop("previous_briefing", None)  # only an input for Claude; already in yesterday's file
        for it in sec["items"]:
            it.pop("_text", None)  # article text is never stored or published

    # Forget old "seen" ids so the state file stays small.
    keep_after = (now - timedelta(days=cfg.get("seen_retention_days", 60))).date().isoformat()
    seen = {k: v for k, v in seen.items() if v >= keep_after}
    save_json(seen_path, seen)
    save_json(pages_path, page_state)

    local = now.astimezone(TZ)
    weekly = None
    if client and local.weekday() >= 5:  # Saturday and Sunday
        weekly = summarize.weekly_review(client, cfg, sections, history[:6])
        if weekly:
            first = (history[:6] or [{"date": today}])[-1]["date"]
            weekly["range"] = f"{datetime.fromisoformat(first):%-d %b} – {local:%-d %b %Y}"
    return {
        "date": today,
        "date_label": local.strftime("%A %d %B %Y"),
        "generated_label": local.strftime("%H:%M %Z"),
        "ai": bool(client),
        "top": top,
        "weekly": weekly,
        "weather": weather.today(cfg.get("location")),
        "sections": sections,
    }


# --------------------------------------------------------------------------- render

def _markdown(text: str) -> Markup:
    # Escape first: the text is model output derived from untrusted web content.
    return Markup(md.markdown(html.escape(text or "", quote=False)))


def _sparkline(values: list[float] | None, w: int = 120, h: int = 28) -> Markup:
    """Inline SVG line that stretches to its container's width."""
    if not values or len(values) < 2:
        return Markup("")
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = w / (len(values) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}"
                   for i, v in enumerate(values))
    color = "var(--up)" if values[-1] >= values[0] else "var(--down)"
    return Markup(f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
                  f'<polyline fill="none" stroke="{color}" stroke-width="1.6" '
                  f'vector-effect="non-scaling-stroke" stroke-linejoin="round" points="{pts}"/></svg>')


def _price(v: float | None) -> str:
    if v is None:
        return "–"
    return f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}"


def _pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "–"
    if round(v, decimals) == 0:
        return f"{0:.{decimals}f}%"
    return f"{v:+.{decimals}f}%".replace("-", "−")


def _updown(v: float | None) -> str:
    if v is None or abs(v) < 0.05:  # anything that displays as 0.0 is flat
        return "flat"
    return "up" if v > 0 else "down"


def _bp(v: float | None) -> str:
    if v is None:
        return "–"
    return "0 bp" if v == 0 else f"{v:+.0f} bp".replace("-", "−")


def _rateval(r: dict) -> str:
    if r.get("unit") == "bp":
        return f"{r['value'] * 100:.0f} bp".replace("-", "−")
    return f"{r['value']:.2f}%".replace("-", "−")


def _shortdate(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%-d %b")
    except (TypeError, ValueError):
        return ""


def _lead(summary: str | None) -> dict:
    """Split a briefing's first bullet into a headline (its bold lead-in) and the rest."""
    first = next((ln.strip()[2:] for ln in (summary or "").splitlines()
                  if ln.strip().startswith(("- ", "* "))), (summary or "").strip())
    m = re.match(r"\*\*(.+?)\*\*[\s:.\-–—]*(.*)", first)
    if m:
        return {"head": m.group(1).strip().rstrip(".:"), "body": m.group(2).strip()}
    head, _, body = first.partition(". ")
    return {"head": head.replace("**", "").strip(), "body": body.replace("**", "").strip()}


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _agenda(d: dict, limit: int = 12) -> list[dict]:
    """All sections' 'On the radar' events in date order, for the front page."""
    try:
        edition = datetime.fromisoformat(d["date"]).date()
    except (KeyError, ValueError):
        return []
    events = []
    for s in d.get("sections", []):
        for e in (s.get("briefing") or {}).get("on_radar") or []:
            when, _, what = e.partition(": ")
            m = (re.search(r"(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+([A-Za-z]{3})", when)
                 or re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})", when))
            if not what or not m:
                continue
            day, mon = (m.group(1), m.group(2)) if m.group(1).isdigit() else (m.group(2), m.group(1))
            if mon.lower() not in MONTHS:
                continue
            try:
                date = edition.replace(month=MONTHS[mon.lower()], day=int(day))
            except ValueError:
                continue
            if date < edition - timedelta(days=60):  # "5 Jan" in an October edition is next year
                date = date.replace(year=date.year + 1)
            if date < edition:
                continue
            clock = re.search(r"\b\d{1,2}:\d{2}\b", when)
            events.append({"date": date, "time": clock.group(0) if clock else "", "what": what.strip(),
                           "section": s["id"], "label": s.get("short") or s["title"]})
    events.sort(key=lambda e: e["date"])
    return events[:limit]


def _curve_svg(c: dict | None) -> Markup:
    """The euro yield curve: today (solid) against 1 month and 1 year ago (dashed)."""
    if not c or not all(v is not None for v in c["now"]):
        return Markup("")
    W, H, L, R, T, B = 640, 260, 8, 46, 12, 26
    lines = [("y1", "var(--faint)", "4 4", "1 year ago"), ("m1", "var(--muted)", "2 3", "1 month ago"),
             ("now", "var(--claret)", "", "Today")]
    vals = [v for k, *_ in lines for v in c[k] if v is not None]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * .12 or .1
    lo, hi = lo - pad, hi + pad
    span = c["tenors"][-1] - c["tenors"][0]
    x = lambda t: L + (t - c["tenors"][0]) / span * (W - L - R)
    y = lambda v: T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
    out = [f'<svg class="curve" viewBox="0 0 {W} {H}" role="img" aria-label="Euro AAA yield curve">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--rule)"/>'
                   f'<text x="{W - R + 6}" y="{y(v) + 4:.1f}" font-size="11" fill="var(--muted)">{v:.2f}%</text>')
    for t in c["tenors"]:
        out.append(f'<text x="{x(t):.1f}" y="{H - 8}" font-size="11" fill="var(--muted)" text-anchor="middle">{t}y</text>')
    for key, color, dash, _ in lines:
        pts = [(x(t), y(v)) for t, v in zip(c["tenors"], c[key]) if v is not None]
        if len(pts) > 1:
            out.append(f'<polyline fill="none" stroke="{color}" stroke-width="{2.4 if key == "now" else 1.6}" '
                       f'stroke-dasharray="{dash}" stroke-linejoin="round" points="'
                       + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>')
    for t, v in zip(c["tenors"], c["now"]):
        out.append(f'<circle cx="{x(t):.1f}" cy="{y(v):.1f}" r="3" fill="var(--claret)"/>')
    out.append("</svg>")
    return Markup("".join(out))


def _calendar(digests: list[dict], today: str) -> str:
    """An iCalendar feed of every upcoming 'Coming up' date from recent editions."""
    import hashlib
    seen, events = set(), []
    for d in digests[:21]:
        for e in _agenda(d, limit=100):
            key = (e["date"], e["what"].lower()[:60])
            if e["date"].isoformat() >= today and key not in seen:
                seen.add(key)
                events.append(e)
    esc = lambda t: t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//The Daily Brief//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:The Daily Brief", "X-PUBLISHED-TTL:PT12H", "REFRESH-INTERVAL;VALUE=DURATION:PT12H"]
    for e in sorted(events, key=lambda e: e["date"]):
        day = e["date"].strftime("%Y%m%d")
        uid = hashlib.sha1(f"{day}{e['what']}".encode()).hexdigest()[:16]
        summary = esc(f"{e['label']}: {e['what']}" + (f" ({e['time']})" if e["time"] else ""))
        lines += ["BEGIN:VEVENT", f"UID:{uid}@daily-brief", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day}", f"SUMMARY:{summary[:250]}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def tile_slug(sec: str, x: dict) -> str:
    """Stable element id for a price/rate tile (ticker links and charts use it)."""
    key = str(x.get("symbol") or x.get("id") or x.get("name") or "").lower()
    for ch in "^=./ ":
        key = key.replace(ch, "")
    return f"t-{sec}-{key if len(key) <= 45 else key[:40]}"


def _charts(d: dict) -> dict:
    """1-year series for each tile, keyed by tile id, for the tap-to-enlarge chart."""
    out = {}
    for s in d["sections"]:
        for q in s.get("quotes") or []:
            if q.get("hist"):
                out[tile_slug(s["id"], q)] = {
                    "name": q["name"], "sub": q["symbol"] + (f" · {q['unit']}" if q.get("unit") else ""),
                    "kind": "price", "points": q["hist"],
                    "url": f"https://finance.yahoo.com/quote/{quote(q['symbol'])}"}
        for r in s.get("rates") or []:
            if r.get("hist"):
                out[tile_slug(s["id"], r)] = {
                    "name": r["name"], "sub": r.get("region", ""), "points": r["hist"],
                    "kind": "bp" if r.get("unit") == "bp" else "pct", "url": r.get("url", "")}
    return out


def _articles(d: dict) -> dict:
    """What the in-app reader shows for each story on the page, keyed by story id.
    `_refs` maps each section to the article ids behind each briefing bullet."""
    out = {"_refs": {s["id"]: (s.get("briefing") or {}).get("summary_refs") or [] for s in d["sections"]}}
    for s in d["sections"]:
        for i in s["items"]:
            out.setdefault(i["id"], {k: v for k, v in {
                "t": i["title"], "l": i.get("url") or i["link"], "sec": s["id"],
                "s": i["sources"][0] if i["sources"] else "", "n": len(i["sources"]),
                "d": i["published"][:10], "sum": i.get("summary", ""), "note": i.get("note", ""),
                "snip": i.get("snippet", "") if i.get("is_new") else "", "img": i.get("image", ""),
            }.items() if v})
    return out


def _search_index(digests: list[dict]) -> dict:
    """Compact index of the last 90 days for the in-app search (search.json)."""
    sections, items, briefs, seen_links = {}, [], [], set()
    for d in digests:
        for s in d["sections"]:
            sections.setdefault(s["id"], s.get("short") or s["title"])
            for i in s["items"]:
                if i.get("is_new") and i["link"] not in seen_links:
                    seen_links.add(i["link"])
                    items.append([d["date"], s["id"], i["title"], i["sources"][0] if i["sources"] else "", i["link"]])
            text = (s.get("briefing") or {}).get("summary")
            if text:
                briefs.append([d["date"], s["id"], text.replace("**", "")])
    return {"sections": sections, "items": items, "briefs": briefs}


def jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters.update(md=_markdown, spark=_sparkline, price=_price, pct=_pct, updown=_updown,
                       bp=_bp, shortdate=_shortdate, lead=_lead, rateval=_rateval,
                       agenda=_agenda, curve=_curve_svg)
    env.globals["tile_slug"] = tile_slug
    return env


def render_site(data_dir: Path, out_dir: Path, cfg: dict | None = None) -> str:
    """Render index.html, one page per day and archive.html. Returns index HTML."""
    env = jinja_env()
    out_dir.mkdir(parents=True, exist_ok=True)
    # App files: manifest, icons and the offline service worker.
    for f in (Path(__file__).parent / "static").iterdir():
        shutil.copy(f, out_dir / f.name)
    # Tab colours and emoji come from the config, so older editions pick them up too.
    style = {s["id"]: s for s in (cfg or {}).get("sections", [])}
    for sid, sec in style.items():
        if sec.get("color"):
            (out_dir / f"icon-cat-{sid}.png").write_bytes(icons.disc_png(sec["color"][0]))
    (out_dir / "badge-72.png").write_bytes(icons.badge_png())
    key = push.private_key()
    env.globals["vapid_public_key"] = push.public_key_b64(key) if key else ""
    # With SITE_PASSPHRASE set, pages and the search index are published encrypted (see lock.py).
    secret = lock.passphrase()
    seal = (lambda html: lock.lock_html(html, secret)) if secret else (lambda html: html)
    files = sorted(data_dir.glob("*.json"), reverse=True)[:SITE_DAYS]
    entries, index_html, digests = [], "", []
    page = env.get_template("digest.html.j2")
    for f in files:
        d = load_json(f, None)
        if not d:
            continue
        for s in d["sections"]:
            s.update({k: style[s["id"]][k] for k in ("emoji", "color")
                      if s["id"] in style and style[s["id"]].get(k)})
        digests.append(d)
        out = page.render(d=d, charts=_charts(d), articles=_articles(d))
        (out_dir / f"{d['date']}.html").write_text(seal(out))
        if not index_html:
            index_html = out
        entries.append({"date": d["date"], "label": d["date_label"],
                        "new_count": sum(s.get("new_count", 0) for s in d["sections"])})
    (out_dir / "index.html").write_text(seal(index_html or "<p>No digest yet.</p>"))
    if digests:  # lets an open app notice that a newer edition exists (only a timestamp)
        (out_dir / "edition.json").write_text(json.dumps(
            {"edition": f"{digests[0]['date']} {digests[0]['generated_label']}"}))
    if digests:
        (out_dir / "calendar.ics").write_text(_calendar(digests, digests[0]["date"]))
    index = json.dumps(_search_index(digests), ensure_ascii=False, separators=(",", ":"))
    (out_dir / "search.json").write_text(lock.lock_json(index, secret) if secret else index)
    (out_dir / "archive.html").write_text(seal(env.get_template("archive.html.j2").render(entries=entries)))
    return index_html  # unencrypted, for the optional e-mail


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
    ap.add_argument("--push", action="store_true",
                    help="send app notifications (needs VAPID_PRIVATE_KEY and PUSH_SUBSCRIPTIONS)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = yaml.safe_load(args.config.read_text())
    digest = None
    if not args.render_only:
        encrypt_stored(args.data, args.state)
        digest = build(cfg, args.state, use_ai=not args.no_ai, data_dir=args.data)
        save_json(args.data / f"{digest['date']}.json", digest)
        log.info("digest %s: %d new articles", digest["date"],
                 sum(s["new_count"] for s in digest["sections"]))
    index_html = render_site(args.data, args.out, cfg)
    if args.email:
        send_email(index_html, os.environ.get("DIGEST_URL", ""))
    if args.push and digest:
        push.notify_all(digest, os.environ.get("DIGEST_URL", ""))


if __name__ == "__main__":
    main()
