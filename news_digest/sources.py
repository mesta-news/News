"""Fetch RSS/Atom feeds, normalise entries, filter, de-duplicate and rank."""

from __future__ import annotations

import hashlib
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; personal-news-digest/1.0)"
TIMEOUT = 20

GOOGLE_NEWS_LOCALES = {
    "nl": ("nl", "NL", "NL:nl"),
    "en": ("en-US", "US", "US:en"),
}


@dataclass
class Item:
    id: str
    title: str
    link: str
    source: str
    published: datetime
    snippet: str = ""
    sources: list[str] = field(default_factory=list)
    is_new: bool = True
    note: str = ""  # filled in by the AI summariser

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "published": self.published.isoformat(),
            "snippet": self.snippet,
            "sources": self.sources,
            "is_new": self.is_new,
            "note": self.note,
        }


def google_news_url(query: str, lang: str = "en") -> str:
    hl, gl, ceid = GOOGLE_NEWS_LOCALES.get(lang, GOOGLE_NEWS_LOCALES["en"])
    return (
        f"https://news.google.com/rss/search?q={quote_plus(query)}"
        f"&hl={hl}&gl={gl}&ceid={ceid}"
    )


def feeds_for_section(section: dict, watchlist: list[dict]) -> list[dict]:
    """All feed definitions ({name, url}) for a section."""
    feeds = list(section.get("feeds") or [])
    for g in section.get("google_news") or []:
        feed = {"name": f"Google News ({g.get('lang', 'en')})",
                "url": google_news_url(g["q"], g.get("lang", "en"))}
        # Optional per-query filters override the section's.
        feed.update({k: g[k] for k in ("keywords", "max_age_days") if k in g})
        feeds.append(feed)
    if section.get("id") == "watchlist":
        for w in watchlist:
            if w.get("news"):
                feeds.append({"name": f"Google News - {w['name']}",
                              "url": google_news_url(w["news"], "en")})
            if not w["symbol"].startswith("^") and "=" not in w["symbol"]:
                feeds.append({
                    "name": f"Yahoo Finance - {w['name']}",
                    "url": "https://feeds.finance.yahoo.com/rss/2.0/headline"
                           f"?s={quote_plus(w['symbol'])}&region=US&lang=en-US",
                })
    return feeds


def _get(url: str) -> bytes:
    path = Path(url.removeprefix("file://"))
    if url.startswith("file://") or (not url.startswith("http") and path.exists()):
        return path.read_bytes()
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _clean_text(raw: str, limit: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:90]


def fetch_feed(feed: dict) -> tuple[list[Item], str | None]:
    """Return (items, error message or None)."""
    try:
        parsed = feedparser.parse(_get(feed["url"]))
    except Exception as exc:  # network errors, HTTP errors
        return [], f"{feed['name']}: {exc}"
    if parsed.bozo and not parsed.entries:
        return [], f"{feed['name']}: could not parse feed"

    is_google = "news.google.com" in feed["url"]
    items = []
    for e in parsed.entries:
        title = _clean_text(e.get("title", ""), 300)
        link = e.get("link", "")
        if not title or not link.startswith(("http://", "https://")):
            continue
        source = feed["name"]
        if is_google:
            # Google News titles look like "Headline - Publisher"
            publisher = (e.get("source") or {}).get("title")
            if publisher:
                source = publisher
                suffix = f" - {publisher}"
                if title.endswith(suffix):
                    title = title[: -len(suffix)]
            snippet = ""  # Google's description just repeats the title
        else:
            snippet = _clean_text(e.get("summary", ""))
        published = _entry_time(e) or datetime.now(timezone.utc)
        items.append(Item(
            id=hashlib.sha1(_title_key(title).encode()).hexdigest()[:12],
            title=title, link=link, source=source, published=published,
            snippet=snippet, sources=[source],
        ))
    return items, None


def collect(section: dict, watchlist: list[dict], now: datetime) -> tuple[list[Item], list[str]]:
    """Fetch all feeds of a section and return ranked, de-duplicated items."""
    items: list[Item] = []
    errors: list[str] = []
    for feed in feeds_for_section(section, watchlist):
        got, err = fetch_feed(feed)
        if err:
            log.warning(err)
            errors.append(err)
        cutoff = now - timedelta(days=feed.get("max_age_days", section.get("max_age_days", 3)))
        keywords = [k.lower() for k in feed.get("keywords", section.get("keywords")) or []]
        items.extend(
            it for it in got
            if it.published >= cutoff
            and (not keywords or any(k in f"{it.title} {it.snippet}".lower() for k in keywords))
        )

    merged: dict[str, Item] = {}
    for it in items:
        existing = merged.get(it.id)
        if existing is None:
            merged[it.id] = it
            continue
        # Same story from another source: remember the extra coverage.
        for s in it.sources:
            if s not in existing.sources:
                existing.sources.append(s)
        if not existing.snippet and it.snippet:
            existing.snippet = it.snippet

    def score(it: Item) -> float:
        hours_old = (now - it.published).total_seconds() / 3600
        return hours_old - 12 * (len(it.sources) - 1)  # coverage beats recency

    return sorted(merged.values(), key=score), errors
