"""Per-exchange trailing stop capabilities (diary simulates exchange rules)."""

from __future__ import annotations

from dataclasses import dataclass

from bot.domain.enums import TrailMode
from bot.domain.exchanges import normalize_exchange


@dataclass(frozen=True)
class TrailingCapabilities:
    native_trailing: bool
    percent: bool
    fixed_distance: bool
    activation_price: bool


EXCHANGE_TRAILING: dict[str, TrailingCapabilities] = {
    "OKX": TrailingCapabilities(True, True, True, True),
    "BINANCE": TrailingCapabilities(True, True, False, True),
    "BYBIT": TrailingCapabilities(True, True, True, True),
    "BITGET": TrailingCapabilities(True, True, False, True),
    "BINGX": TrailingCapabilities(True, True, True, True),
    "MEXC": TrailingCapabilities(True, True, True, True),
    "HYPERLIQUID": TrailingCapabilities(False, False, False, False),
}


def trailing_capabilities(exchange: str) -> TrailingCapabilities:
    return EXCHANGE_TRAILING.get(normalize_exchange(exchange), TrailingCapabilities(False, False, False, False))


def validate_trailing_for_exchange(
    exchange: str,
    mode: TrailMode,
    *,
    has_activation: bool,
) -> str | None:
    caps = trailing_capabilities(exchange)
    if mode == TrailMode.FIXED:
        return None
    if not caps.native_trailing:
        return f"{normalize_exchange(exchange)} has no native trailing stop — use fixed SL: price"
    if mode == TrailMode.PERCENT and not caps.percent:
        return f"{normalize_exchange(exchange)} supports trailing distance only, not percent"
    if mode == TrailMode.DISTANCE and not caps.fixed_distance:
        return f"{normalize_exchange(exchange)} supports trailing percent only, not fixed distance"
    if has_activation and not caps.activation_price:
        return f"{normalize_exchange(exchange)} does not support activation price for trailing"
    return None
