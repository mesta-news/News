"""Open the articles the page shows, so Claude can summarise them for the in-app reader.

For each article we resolve Google News redirect links to the publisher's URL,
download the page and keep its main text (only as input for Claude, never
stored or published) and its preview image link (og:image). Everything here is
best effort: paywalls, blocked sites and timeouts just leave the article without
a summary, and the reader falls back to the feed snippet.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

TIMEOUT = 12
TEXT_LIMIT = 3500  # characters of article text handed to Claude (enough for key points)
HEADERS = {
    # A normal browser user agent: many news sites refuse unknown clients.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Accept-Language": "en,nl;q=0.8",
}


def _google_id(url: str) -> str | None:
    m = re.search(r"news\.google\.com/(?:rss/)?articles/([^?/#]+)", url)
    return m.group(1) if m else None


def resolve(url: str, session: requests.Session) -> str:
    """The publisher's URL for a Google News link (unchanged for other links)."""
    gid = _google_id(url)
    if not gid:
        return url
    # Older ids embed the target URL directly in a base64 protobuf.
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4)).decode("latin1")
        m = re.search(r"https?://[\x21-\x7e]+", raw)
        if m and "AU_yqL" not in raw:
            return m.group(0)
    except ValueError:
        pass
    # Newer ids need Google's own decoding endpoint (signature + timestamp from the article page).
    try:
        page = session.get(f"https://news.google.com/rss/articles/{gid}", timeout=TIMEOUT).text
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            return url
        req = ["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,'
                         f'null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sg.group(1)}"]']
        resp = session.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                            data={"f.req": json.dumps([[req]])}, timeout=TIMEOUT,
                            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        body = json.loads(resp.text.split("\n\n", 1)[1])
        return json.loads(body[0][2])[1]
    except Exception as exc:  # the format changes from time to time
        log.debug("google news decode failed for %s: %s", gid, exc)
        return url


def extract(html: str, base_url: str) -> tuple[str, str]:
    """(main text, preview image URL) from an article page."""
    soup = BeautifulSoup(html, "html.parser")
    image = ""
    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content", "").strip():
            image = urljoin(base_url, tag["content"].strip())
            break
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "figure"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [" ".join(p.get_text(" ", strip=True).split()) for p in root.find_all("p")]
    text, total = [], 0
    for p in paragraphs:
        if len(p) < 60 or p.lower().startswith(("cookie", "subscribe", "sign up", "advertisement")):
            continue
        text.append(p)
        total += len(p)
        if total >= TEXT_LIMIT:
            break
    return " ".join(text)[:TEXT_LIMIT], image if image.startswith("https://") else ""


def _fetch(item: dict) -> None:
    with requests.Session() as session:
        session.headers.update(HEADERS)
        try:
            url = resolve(item["link"], session)
            if url != item["link"]:
                item["url"] = url  # the publisher's own link, used by "Read at source"
            resp = session.get(url, timeout=TIMEOUT)
            if resp.ok and "html" in resp.headers.get("Content-Type", "html"):
                text, image = extract(resp.text, resp.url)
                if len(text) >= 200:
                    item["_text"] = text  # input for Claude only; removed before saving
                if image:
                    item["image"] = image
        except requests.RequestException as exc:
            log.debug("article %s: %s", item["link"], exc)


def enrich(sections: list[dict], per_section: int = 8) -> None:
    """Fetch the top new articles of every section in parallel (adds url, image, _text)."""
    todo = [i for s in sections for i in [x for x in s["items"] if x["is_new"]][:per_section]]
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(_fetch, todo))
    drop_generic_images(todo)
    got = sum(1 for i in todo if i.get("_text"))
    log.info("articles: read %d of %d shown articles", got, len(todo))


GENERIC = re.compile(r"logo|default|placeholder|fallback|favicon|icon|share[-_]?image|og[-_]?image|brand", re.I)


FILE_NOISE = {"image", "images", "photo", "featured", "thumb", "thumbnail", "scaled", "copy", "large", "medium",
              "small", "header", "hero", "cover", "jpeg", "webp", "wide", "crop", "upload", "uploads", "content",
              "article", "news", "final", "edit", "main", "getty", "shutterstock", "reuters", "istock"}


def image_matches_title(image: str, title: str) -> bool:
    """False when the picture's file name clearly names a subject the headline doesn't
    mention (e.g. gta-6-trailer.jpg on an OpenAI story); unnamed files pass."""
    name = re.sub(r"\.[a-z0-9]{2,5}$", "", image.rsplit("/", 1)[-1].split("?")[0].lower())
    words = {w for w in re.findall(r"[a-z]{4,}", name) if w not in FILE_NOISE}
    if len(words) < 2:
        return True
    head = title.lower()
    return any(w in head or w[:5] in head for w in words)


def drop_generic_images(items: list[dict]) -> None:
    """Remove pictures that don't belong to the story: site logos and default share
    images, and any image a site reuses for several different articles."""
    from collections import Counter
    uses = Counter(i["image"] for i in items if i.get("image"))
    for i in items:
        img = i.get("image")
        if img and (uses[img] > 1 or GENERIC.search(img.rsplit("/", 1)[-1])
                    or not image_matches_title(img, i.get("title", ""))):
            del i["image"]
