"""'Something big happened' signals that decide which tabs send a notification.

Two kinds, both stored on the section as `alerts` (a list of short texts):
  * data rules here: a large one-day price move, or a policy/market rate that
    moved more than its `alert_bp` since the previous edition;
  * Claude's judgement: the section briefing's `alert` field (see summarize.py).
"""

from __future__ import annotations


def move_threshold(entry: dict) -> float:
    """One-day % move that counts as big for an instrument (override with `alert:`)."""
    if entry.get("alert") is not None:
        return float(entry["alert"])
    sym = entry["symbol"]
    if sym == "^VIX":
        return 15.0
    if sym.endswith("=X"):  # currencies move little
        return 1.2
    if sym.endswith("=F"):  # oil, gas, gold
        return 4.0
    if sym.startswith("^") or entry.get("group") == "Indices":
        return 2.0
    return 5.0  # single stocks


def market_alerts(quotes: list[dict], defs: list[dict]) -> list[str]:
    by_symbol = {d["symbol"]: d for d in defs}
    out = []
    for q in quotes:
        d1 = q.get("d1")
        if d1 is None or q["symbol"] not in by_symbol:
            continue
        if abs(d1) >= move_threshold(by_symbol[q["symbol"]]):
            sign = "+" if d1 > 0 else "−"
            out.append(f"{q['name']} {sign}{abs(d1):.1f}% on the day")
    return out


def rate_alerts(rows: list[dict], defs: list[dict], previous: dict[str, float]) -> list[str]:
    """Rates with `alert_bp:` that moved at least that much since the last edition."""
    out = []
    for row, d in zip(rows, defs):
        limit = d.get("alert_bp")
        old = previous.get(row["name"])
        if limit is None or row.get("value") is None or old is None:
            continue
        scale = 1 if row.get("unit") == "bp" else 100  # % values -> basis points
        moved = round((row["value"] - old) * scale)
        if abs(moved) >= limit:
            now = (f"{row['value'] * 100:.0f} bp" if row.get("unit") == "bp" else f"{row['value']:.2f}%")
            out.append(f"{row['name']} {'+' if moved > 0 else '−'}{abs(moved)} bp to {now}")
    return out
