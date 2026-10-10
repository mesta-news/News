"""Watchlist quotes from Yahoo Finance (via yfinance)."""

from __future__ import annotations

import logging
import math
from datetime import datetime

log = logging.getLogger(__name__)


def _pct(new: float, old: float | None) -> float | None:
    if old is None or not old or math.isnan(old) or math.isnan(new):
        return None
    return (new / old - 1) * 100


def quotes(watchlist: list[dict], now: datetime) -> tuple[list[dict], str | None]:
    """Return (rows, error). Each row has price, % changes and a sparkline series."""
    if not watchlist:
        return [], None
    try:
        import yfinance as yf

        symbols = [w["symbol"] for w in watchlist]
        data = yf.download(symbols, period="1y", interval="1d", group_by="ticker",
                           auto_adjust=True, progress=False, threads=True)
    except Exception as exc:
        log.warning("quotes: %s", exc)
        return [], f"Could not load quotes: {exc}"

    rows = []
    for w in watchlist:
        row = {"symbol": w["symbol"], "name": w["name"], "group": w.get("group", ""),
               "unit": w.get("unit", ""), "price": None}
        try:
            closes = data[w["symbol"]]["Close"].dropna()
        except Exception:
            closes = None
        if closes is None or closes.empty:
            rows.append(row)
            continue
        vals = [float(v) for v in closes.tolist()]
        dates = closes.index
        last = vals[-1]
        this_year = [v for v, d in zip(vals, dates) if d.year == now.year]
        year_start = vals[len(vals) - len(this_year) - 1] if len(this_year) < len(vals) else this_year[0]
        row.update(
            price=last,
            as_of=dates[-1].strftime("%Y-%m-%d"),
            d1=_pct(last, vals[-2] if len(vals) > 1 else None),
            w1=_pct(last, vals[-6] if len(vals) > 5 else None),
            m1=_pct(last, vals[-22] if len(vals) > 21 else None),
            ytd=_pct(last, year_start),
            spark=vals[-66:],  # ~3 months
            # ~1 year for the tap-to-enlarge chart: every other trading day, plus the last one
            hist=[[d.strftime("%Y-%m-%d"), round(v, 4)] for d, v in
                  list(zip(dates, vals))[-252::2] + ([(dates[-1], vals[-1])] if len(vals) % 2 == 0 else [])],
        )
        rows.append(row)
    if all(r["price"] is None for r in rows):
        return rows, "No quotes returned by Yahoo Finance."
    return rows, None
