"""Watch official web pages and report when their text changes."""

from __future__ import annotations

import difflib
import hashlib
import logging
import re

from bs4 import BeautifulSoup

from .sources import _get

log = logging.getLogger(__name__)

MAX_DIFF_LINES = 40


def page_text(raw: bytes) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.body or soup
    lines = (re.sub(r"\s+", " ", ln).strip() for ln in main.get_text("\n").splitlines())
    return "\n".join(ln for ln in lines if len(ln) > 2)


def check(pages: list[dict], state: dict, today: str) -> list[dict]:
    """Compare each page with the stored copy in `state` (updated in place).

    Returns one entry per page: status is "new" (first time seen), "unchanged",
    "changed" (with a diff) or "error".
    """
    results = []
    for page in pages:
        url = page["url"]
        entry = {"name": page["name"], "url": url, "status": "unchanged", "diff": ""}
        try:
            text = page_text(_get(url))
        except Exception as exc:
            log.warning("watch page %s: %s", url, exc)
            entry.update(status="error", diff=f"Could not fetch page ({exc}). Check the URL in config.yaml.")
            results.append(entry)
            continue

        digest = hashlib.sha256(text.encode()).hexdigest()
        prev = state.get(url)
        if prev is None:
            entry["status"] = "new"
        elif prev["hash"] != digest:
            diff = difflib.unified_diff(
                prev["text"].splitlines(), text.splitlines(), lineterm="", n=1
            )
            changed = [ln for ln in diff if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
            entry["status"] = "changed"
            entry["diff"] = "\n".join(changed[:MAX_DIFF_LINES])
            if len(changed) > MAX_DIFF_LINES:
                entry["diff"] += f"\n… ({len(changed) - MAX_DIFF_LINES} more changed lines)"
        if prev is None or prev["hash"] != digest:
            state[url] = {"hash": digest, "text": text, "changed": today}
        entry["last_changed"] = state[url]["changed"]
        results.append(entry)
    return results
