"""Key interest rates.

Sources (pick per series in config.yaml with `source:`):
  ecb   - ECB Data Portal (official euro rates, yield curve); id = "FLOW/KEY",
          e.g. "EST/B.EU000A2X2A25.WT" for €STR. Browse https://data.ecb.europa.eu
  yahoo - Yahoo Finance yield tickers, e.g. "^TNX" (US 10-year)
  fred  - FRED (St. Louis Fed); id = series id. Often unreachable from GitHub.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import quote

import requests

from .sources import USER_AGENT, _get

log = logging.getLogger(__name__)

TIMEOUT = 45
HISTORY_DAYS = 400
ECB_CSV = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&startPeriod={start}"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"


def _http(url: str) -> bytes:
    if not url.startswith("http"):
        return _get(url)  # local test fixtures
    for attempt in (1, 2):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def _parse_date(text: str) -> date:
    # Daily "2026-10-09", monthly "2026-09", quarterly "2026-Q3"
    if "Q" in text:
        year, q = text.split("-Q")
        return date(int(year), int(q) * 3, 1)
    return date.fromisoformat(text if len(text) == 10 else text + "-01")


def _ecb(series_id: str, start: date) -> list[tuple[date, float]]:
    flow, key = series_id.split("/", 1)
    raw = _http(ECB_CSV.format(flow=flow, key=key, start=start.isoformat()))
    out = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        try:
            out.append((_parse_date(row["TIME_PERIOD"]), float(row["OBS_VALUE"])))
        except (KeyError, ValueError):
            continue
    return sorted(out)


def _fred(series_id: str, start: date) -> list[tuple[date, float]]:
    rows = csv.reader(io.StringIO(_http(FRED_CSV.format(id=series_id, start=start)).decode()))
    next(rows, None)  # header
    out = []
    for row in rows:
        try:
            out.append((date.fromisoformat(row[0]), float(row[1])))
        except (ValueError, IndexError):
            continue  # FRED marks missing days with "."
    return out


def _yahoo(symbol: str, start: date) -> list[tuple[date, float]]:
    import yfinance as yf

    closes = yf.Ticker(symbol).history(start=start.isoformat(), auto_adjust=False)["Close"].dropna()
    return [(ts.date(), float(v)) for ts, v in closes.items()]


FETCHERS = {"ecb": _ecb, "fred": _fred, "yahoo": _yahoo}


def source_url(d: dict) -> str:
    source, sid = d.get("source", "fred"), d["id"]
    if source == "ecb":
        return f"https://data.ecb.europa.eu/data/datasets/{sid.split('/')[0]}/{sid.replace('/', '.')}"
    if source == "yahoo":
        return f"https://finance.yahoo.com/quote/{quote(sid)}"
    return f"https://fred.stlouisfed.org/series/{quote(sid)}"


def _value_on_or_before(series: list[tuple[date, float]], day: date) -> float | None:
    earlier = [v for d, v in series if d <= day]
    return earlier[-1] if earlier else None


def _thin(values: list[float], points: int = 60) -> list[float]:
    step = max(1, len(values) // points)
    return values[::step] + ([values[-1]] if values and (len(values) - 1) % step else [])


def _bp(new: float, old: float | None) -> float | None:
    return None if old is None else round((new - old) * 100)


def fetch(defs: list[dict]) -> tuple[list[dict], str | None]:
    """Return (rows, error). Each row: name, region, value (%), as_of, m1/y1 change in bp."""
    start = date.today() - timedelta(days=HISTORY_DAYS)

    def one(d: dict) -> dict:
        row = {"id": d["id"], "name": d["name"], "region": d.get("region", ""),
               "url": source_url(d), "value": None}
        try:
            series = FETCHERS[d.get("source", "fred")](d["id"], start)
        except Exception as exc:
            log.warning("rate %s (%s): %s", d["id"], d.get("source", "fred"), exc)
            return row
        if not series:
            log.warning("rate %s: no observations", d["id"])
            return row
        last_day, last = series[-1]
        row.update(
            value=last,
            as_of=last_day.isoformat(),
            m1=_bp(last, _value_on_or_before(series, last_day - timedelta(days=30))),
            y1=_bp(last, _value_on_or_before(series, last_day - timedelta(days=365))),
            spark=_thin([v for d_, v in series if d_ >= last_day - timedelta(days=365)]),
        )
        return row

    if not defs:
        return [], None
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(one, defs))
    if all(r["value"] is None for r in rows):
        return rows, "Could not load interest rates."
    return rows, None
