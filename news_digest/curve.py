"""The euro AAA government yield curve (ECB) today, a month ago and a year ago."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .rates import HISTORY_DAYS, _ecb, _value_on_or_before

log = logging.getLogger(__name__)

TENORS = [1, 2, 3, 5, 7, 10, 15, 20, 30]
SERIES = "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{}Y"


def fetch() -> dict | None:
    start = date.today() - timedelta(days=HISTORY_DAYS)
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            series = list(pool.map(lambda n: _ecb(SERIES.format(n), start), TENORS))
    except Exception as exc:
        log.warning("yield curve: %s", exc)
        return None
    if not all(series):
        return None
    last = min(s[-1][0] for s in series)  # a day every tenor has
    at = lambda day: [_value_on_or_before(s, day) for s in series]
    return {"tenors": TENORS, "as_of": last.isoformat(), "now": at(last),
            "m1": at(last - timedelta(days=30)), "y1": at(last - timedelta(days=365))}
