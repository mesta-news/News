"""Key interest rates from FRED (St. Louis Fed). Public CSV downloads, no API key."""

from __future__ import annotations

import csv
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests

from .sources import USER_AGENT, _get

log = logging.getLogger(__name__)

# cosd = start date: download ~13 months instead of the full history (FRED is slow on big files).
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"
TIMEOUT = 45


def _download(series_id: str) -> bytes:
    start = (date.today() - timedelta(days=400)).isoformat()
    url = FRED_CSV.format(id=series_id, start=start)
    if not url.startswith("http"):
        return _get(url.split("&", 1)[0])  # local test fixtures
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


def _series(series_id: str) -> list[tuple[date, float]]:
    rows = csv.reader(io.StringIO(_download(series_id).decode()))
    next(rows, None)  # header
    out = []
    for row in rows:
        try:
            out.append((date.fromisoformat(row[0]), float(row[1])))
        except (ValueError, IndexError):
            continue  # FRED marks missing days with "."
    return out


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
    def one(d: dict) -> dict:
        row = {"id": d["id"], "name": d["name"], "region": d.get("region", ""), "value": None}
        try:
            series = _series(d["id"])
        except Exception as exc:
            log.warning("rate %s: %s", d["id"], exc)
            return row
        if not series:
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
        return rows, "Could not load interest rates from FRED."
    return rows, None
