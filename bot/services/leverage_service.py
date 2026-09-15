"""Max leverage per exchange + symbol (public APIs, cached)."""

import time

from bot.domain.exchanges import normalize_exchange
from bot.services.price_service import _base_symbol, _bingx_symbol, _get_json, _normalize_pair, _post_json

_CACHE: dict[tuple[str, str], tuple[int, float]] = {}
_CACHE_TTL = 3600.0

# Fallback when API is unavailable (exchange-wide typical max)
_EXCHANGE_DEFAULT_MAX: dict[str, int] = {
    "BINANCE": 125,
    "OKX": 100,
    "BYBIT": 100,
    "BITGET": 125,
    "BINGX": 150,
    "MEXC": 200,
    "HYPERLIQUID": 50,
}


def _cache_get(exchange: str, symbol: str) -> int | None:
    key = (exchange, _normalize_pair(symbol))
    entry = _CACHE.get(key)
    if entry and time.monotonic() - entry[1] < _CACHE_TTL:
        return entry[0]
    return None


def _cache_set(exchange: str, symbol: str, max_lev: int) -> None:
    _CACHE[(exchange, _normalize_pair(symbol))] = (max_lev, time.monotonic())


async def _fetch_bybit(pair: str) -> int | None:
    data = await _get_json(
        f"https://api.bybit.com/v5/market/instruments-info?category=linear&symbol={pair}"
    )
    items = (data or {}).get("result", {}).get("list", [])
    if items and items[0].get("leverageFilter"):
        return int(float(items[0]["leverageFilter"]["maxLeverage"]))
    return None


async def _fetch_okx(base: str) -> int | None:
    for inst in (f"{base}-USDT-SWAP", f"{base}-USDT"):
        data = await _get_json(
            f"https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId={inst}"
        )
        if data and data.get("data"):
            return int(float(data["data"][0]["lever"]))
    return None


async def _fetch_binance(pair: str) -> int | None:
    data = await _get_json(
        "https://www.binance.com/bapi/futures/v1/friendly/future/common/brackets"
        f"?symbol={pair}"
    )
    brackets = (data or {}).get("data", {}).get("brackets") or (data or {}).get("data")
    if isinstance(brackets, list) and brackets:
        return max(int(float(b.get("initialLeverage", b.get("maxOpenPosLeverage", 0)))) for b in brackets)
    data = await _get_json(f"https://fapi.binance.com/fapi/v1/exchangeInfo?symbol={pair}")
    symbols = (data or {}).get("symbols", [])
    if symbols:
        for f in symbols[0].get("filters", []):
            if f.get("filterType") == "MAX_LEVERAGE":
                return int(float(f["maxLeverage"]))
    return None


async def _fetch_bitget(pair: str) -> int | None:
    data = await _get_json(
        f"https://api.bitget.com/api/v2/mix/market/contracts"
        f"?productType=USDT-FUTURES&symbol={pair}"
    )
    if data and data.get("data"):
        d = data["data"]
        item = d[0] if isinstance(d, list) else d
        for key in ("maxLever", "maxLeverage", "max_lever"):
            if item.get(key) is not None:
                return int(float(item[key]))
    return None


async def _fetch_bingx(pair: str) -> int | None:
    data = await _get_json(
        f"https://open-api.bingx.com/openApi/swap/v2/quote/contracts?symbol={_bingx_symbol(pair)}"
    )
    items = (data or {}).get("data", [])
    if isinstance(items, list) and items:
        item = items[0]
        for key in ("maxLeverage", "maxLongLeverage", "maxShortLeverage"):
            if item.get(key) is not None:
                return int(float(item[key]))
    return None


async def _fetch_mexc(base: str) -> int | None:
    data = await _get_json(
        f"https://contract.mexc.com/api/v1/contract/detail?symbol={base}_USDT"
    )
    payload = (data or {}).get("data")
    if isinstance(payload, dict):
        for key in ("maxLeverage", "max_leverage"):
            if payload.get(key) is not None:
                return int(float(payload[key]))
    return None


async def _fetch_hyperliquid(base: str) -> int | None:
    data = await _post_json("https://api.hyperliquid.xyz/info", {"type": "meta"})
    if not isinstance(data, dict):
        return None
    for asset in data.get("universe", []):
        name = asset.get("name", "")
        if name == base or name == f"k{base}":
            return int(asset["maxLeverage"])
    return None


async def _fetch_max_leverage(exchange: str, symbol: str) -> int:
    exchange = normalize_exchange(exchange)
    pair = _normalize_pair(symbol)
    base = _base_symbol(symbol)

    max_lev: int | None = None
    if exchange == "BYBIT":
        max_lev = await _fetch_bybit(pair)
    elif exchange == "OKX":
        max_lev = await _fetch_okx(base)
    elif exchange == "BINANCE":
        max_lev = await _fetch_binance(pair)
    elif exchange == "BITGET":
        max_lev = await _fetch_bitget(pair)
    elif exchange == "BINGX":
        max_lev = await _fetch_bingx(pair)
    elif exchange == "MEXC":
        max_lev = await _fetch_mexc(base)
    elif exchange == "HYPERLIQUID":
        max_lev = await _fetch_hyperliquid(base)

    if max_lev is None or max_lev < 1:
        max_lev = _EXCHANGE_DEFAULT_MAX.get(exchange, 100)

    _cache_set(exchange, symbol, max_lev)
    return max_lev


async def get_max_leverage(exchange: str, symbol: str) -> int:
    exchange = normalize_exchange(exchange)
    cached = _cache_get(exchange, symbol)
    if cached is not None:
        return cached
    return await _fetch_max_leverage(exchange, symbol)


async def validate_leverage(exchange: str, symbol: str, leverage: int) -> str | None:
    if leverage < 1:
        return "Leverage must be >= 1"
    max_lev = await get_max_leverage(exchange, symbol)
    if leverage > max_lev:
        sym = _base_symbol(symbol)
        return f"Max leverage for {sym} on {exchange} is {max_lev}x (you sent {leverage}x)"
    return None


def normalize_leverage_value(leverage: int) -> int:
    """Fix sign only — max is validated separately per exchange/symbol."""
    return abs(leverage)
