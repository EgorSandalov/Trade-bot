"""Format trades as setup text and parse edit submissions."""

from __future__ import annotations

import re
from html import escape

from bot.domain.enums import EntryType, LevelStatus
from bot.domain.models import Trade
from bot.domain.numbers import parse_number
from bot.domain.parser import TP_PATTERN, parse_trade_message
from bot.domain.trailing import format_sl_line

_REASON_PREFIX = re.compile(r"^reason\s*:", re.IGNORECASE)


def _plain_price(v: float) -> str:
    if v >= 100:
        return f"{v:,.0f}".replace(",", "")
    return f"{v:.4f}".rstrip("0").rstrip(".")


def split_edit_message(text: str) -> tuple[str, str | None]:
    """Separate optional ``Reason: ...`` line from setup body."""
    lines = text.strip().splitlines()
    body: list[str] = []
    reason: str | None = None
    for line in lines:
        stripped = line.strip()
        if _REASON_PREFIX.match(stripped):
            reason = stripped.split(":", 1)[1].strip() or None
        elif stripped:
            body.append(stripped)
    return "\n".join(body), reason


def parse_indexed_take_profits(text: str) -> list[tuple[int, float, float]]:
    result: list[tuple[int, float, float]] = []
    for line in text.strip().splitlines():
        m = TP_PATTERN.match(line.strip())
        if m:
            idx = int(m.group(1))
            price = parse_number(m.group(2))
            pct = parse_number(m.group(3))
            result.append((idx, price, pct))
    return result


def format_trade_setup(trade: Trade, *, include_reason_hint: bool = False) -> str:
    """Editable setup lines — triggered TPs are omitted (still shown in the card)."""
    sym = trade.symbol.replace("USDT", "")
    lines = [
        trade.exchange.upper(),
        sym,
        trade.side.value.upper(),
        f"Type: {trade.entry_type.value}",
        f"Leverage: {trade.leverage}",
    ]

    if trade.entry_type != EntryType.MARKET:
        lines.append(f"Entry: {_plain_price(trade.entry_price)}")

    if trade.stop_loss:
        lines.append(format_sl_line(trade.stop_loss))

    for tp in sorted(trade.take_profits, key=lambda t: t.order_index):
        if tp.status == LevelStatus.TRIGGERED:
            continue
        lines.append(f"TP{tp.order_index}: {_plain_price(tp.price)} - {tp.close_percent:.0f}%")

    if trade.comment:
        lines.append(f"Comment: {trade.comment}")

    if include_reason_hint:
        lines.append("Reason: optional — why you changed parameters")

    return "\n".join(lines)


def format_edit_context(trade: Trade) -> str:
    """Human-readable constraints shown above the template."""
    parts: list[str] = [
        "⚙️ <b>Edit trade</b>",
        "",
        "Copy the template, change the lines you need, and send it back.",
        "Optional last line: Reason: why you changed",
        "Tap ◀ Back to return without saving.",
        "",
        "⏸ SL/TP monitoring is <b>paused</b> until you finish or tap Back.",
        "",
        "Do not change exchange, pair, direction, or Type.",
        "SL / trailing and pending TPs are checked vs <b>current market</b>.",
        "Trailing: <code>SL: trail 0,5%</code> or fixed + <code>SL: trail 0,5% - 80000</code>",
    ]

    triggered = [tp for tp in trade.take_profits if tp.status == LevelStatus.TRIGGERED]
    if triggered:
        hit = ", ".join(
            f"TP{tp.order_index} ({tp.close_percent:.0f}%)" for tp in triggered
        )
        parts.append(f"Already hit: {hit} — do not add these TPs again.")
        parts.append(f"Remaining to allocate in TPs: <b>{trade.remaining_percent:.0f}%</b>")
    else:
        parts.append("Sum of TP close % must be ≤ 100%.")

    parts.extend([
        "Copy the template below and send your changes:",
        "",
        "<pre>" + escape(format_trade_setup(trade)) + "</pre>",
    ])
    return "\n".join(parts)
