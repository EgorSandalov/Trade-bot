"""Публичные API бирж для автоматического мониторинга цен (TP/SL, ручное закрытие)."""

import time
from datetime import datetime, timedelta, timezone

import aiohttp

from bot.domain.candles import Candle
from bot.domain.exchanges import SUPPORTED_EXCHANGES, normalize_exchange

# Re-export for backward compatibility
__all__ = ["SUPPORTED_EXCHANGES", "fetch_price", "fetch_candles", "normalize_exchange"]

_hl_mids: dict[str, float] | None = None
_hl_mids_ts: float = 0.0
_HL_CACHE_TTL = 5.0


def _normalize_pair(symbol: str) -> str:
    s = symbol.upper().replace("/", "")
    if not s.endswith("USDT"):
        s += "USDT"
    return s


def _base_symbol(symbol: str) -> str:
    s = symbol.upper().replace("/", "")
    return s[:-4] if s.endswith("USDT") else s


def _bingx_symbol(pair: str) -> str:
    return _normalize_pair(pair).replace("USDT", "-USDT")


def _chunk_end_ms(start_ms: int, end_ms: int, *, max_minutes: int = 999) -> int:
    """Cap one API request window (Bybit/Bitget return newest N candles in range)."""
    return min(end_ms, start_ms + max_minutes * 60_000)


async def _get_json(url: str) -> dict | list | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        return None
    return None


async def _post_json(url: str, payload: dict) -> dict | list | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        return None
    return None


async def _hyperliquid_mids() -> dict[str, float]:
    global _hl_mids, _hl_mids_ts
    now = time.monotonic()
    if _hl_mids is not None and now - _hl_mids_ts < _HL_CACHE_TTL:
        return _hl_mids

    data = await _post_json("https://api.hyperliquid.xyz/info", {"type": "allMids"})
    if isinstance(data, dict):
        _hl_mids = {
            coin: float(price)
            for coin, price in data.items()
            if isinstance(price, str) and not coin.startswith("@")
        }
        _hl_mids_ts = now
        return _hl_mids
    return _hl_mids or {}


async def _fetch_hyperliquid(symbol: str) -> float | None:
    base = _base_symbol(symbol)
    mids = await _hyperliquid_mids()
    if base in mids:
        return mids[base]
    # kPEPE → иногда на HL тикер с префиксом k
    if f"k{base}" in mids:
        return mids[f"k{base}"]
    return None


async def _fetch_mexc(symbol: str) -> float | None:
    base = _base_symbol(symbol)
    pair = _normalize_pair(symbol)
    mexc_sym = f"{base}_USDT"

    data = await _get_json(
        f"https://contract.mexc.com/api/v1/contract/ticker?symbol={mexc_sym}"
    )
    if data and data.get("success"):
        payload = data.get("data")
        if isinstance(payload, list) and payload:
            return float(payload[0]["lastPrice"])
        if isinstance(payload, dict) and payload.get("lastPrice") is not None:
            return float(payload["lastPrice"])

    data = await _get_json(f"https://api.mexc.com/api/v3/ticker/price?symbol={pair}")
    if data and data.get("price"):
        return float(data["price"])
    return None


def _ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _parse_ohlc(raw: list, ts_idx: int = 0, o_idx: int = 1, h_idx: int = 2, l_idx: int = 3, c_idx: int = 4) -> Candle:
    ts_raw = raw[ts_idx]
    ts_ms = int(ts_raw) if int(ts_raw) > 10_000_000_000 else int(ts_raw) * 1000
    return Candle(
        ts=_from_ms(ts_ms),
        open=float(raw[o_idx]),
        high=float(raw[h_idx]),
        low=float(raw[l_idx]),
        close=float(raw[c_idx]),
    )


async def _fetch_binance_candles(pair: str, start_ms: int, end_ms: int) -> list[Candle]:
    for base in ("https://fapi.binance.com/fapi/v1/klines", "https://api.binance.com/api/v3/klines"):
        data = await _get_json(
            f"{base}?symbol={pair}&interval=1m&startTime={start_ms}&endTime={end_ms}&limit=1500"
        )
        if isinstance(data, list) and data:
            return [_parse_ohlc(row) for row in data]
    return []


async def _fetch_okx_candles(base: str, start_ms: int, end_ms: int) -> list[Candle]:
    """OKX history-candles: ``after`` = return candles older than this timestamp."""
    for inst in (f"{base}-USDT-SWAP", f"{base}-USDT"):
        candles: dict[int, Candle] = {}
        cursor = end_ms + 60_000
        for _ in range(50):
            data = await _get_json(
                "https://www.okx.com/api/v5/market/history-candles"
                f"?instId={inst}&bar=1m&after={cursor}&limit=300"
            )
            rows = (data or {}).get("data") or []
            if not rows:
                break
            batch = [_parse_ohlc(row) for row in rows]
            oldest_ms = min(_ms(c.ts) for c in batch)
            for c in batch:
                ts = _ms(c.ts)
                if start_ms <= ts <= end_ms:
                    candles[ts] = c
            if oldest_ms <= start_ms:
                break
            cursor = oldest_ms
        if candles:
            return sorted(candles.values(), key=lambda c: c.ts)
    return []


async def _fetch_bybit_candles(pair: str, start_ms: int, end_ms: int) -> list[Candle]:
    chunk_end = _chunk_end_ms(start_ms, end_ms)
    data = await _get_json(
        "https://api.bybit.com/v5/market/kline"
        f"?category=linear&symbol={pair}&interval=1&start={start_ms}&end={chunk_end}&limit=1000"
    )
    rows = (data or {}).get("result", {}).get("list") or []
    if not rows:
        return []
    # Bybit returns newest first
    candles = [_parse_ohlc(row, ts_idx=0, o_idx=1, h_idx=2, l_idx=3, c_idx=4) for row in rows]
    return list(reversed(candles))


async def _fetch_bitget_candles(pair: str, start_ms: int, end_ms: int) -> list[Candle]:
    chunk_end = _chunk_end_ms(start_ms, end_ms)
    data = await _get_json(
        "https://api.bitget.com/api/v2/mix/market/candles"
        f"?symbol={pair}&productType=USDT-FUTURES&granularity=1m"
        f"&startTime={start_ms}&endTime={chunk_end}&limit=1000"
    )
    rows = (data or {}).get("data") or []
    if not rows:
        return []
    candles = [_parse_ohlc(row) for row in rows]
    return list(reversed(candles))


async def _fetch_mexc_candles(base: str, start_ms: int, end_ms: int) -> list[Candle]:
    sym = f"{base}_USDT"
    start_s = start_ms // 1000
    end_s = end_ms // 1000
    data = await _get_json(
        f"https://contract.mexc.com/api/v1/contract/kline/{sym}"
        f"?interval=Min1&start={start_s}&end={end_s}"
    )
    if not data or not data.get("success"):
        return []
    payload = data.get("data") or {}
    times = payload.get("time") or []
    if not times:
        return []
    return [
        Candle(
            ts=_from_ms(int(t) * 1000),
            open=float(payload["open"][i]),
            high=float(payload["high"][i]),
            low=float(payload["low"][i]),
            close=float(payload["close"][i]),
        )
        for i, t in enumerate(times)
    ]


async def _fetch_bingx_candles(pair: str, start_ms: int, end_ms: int) -> list[Candle]:
    sym = _bingx_symbol(pair)
    data = await _get_json(
        "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        f"?symbol={sym}&interval=1m&startTime={start_ms}&limit=1000"
    )
    rows = (data or {}).get("data") or []
    if not rows:
        return []
    candles = []
    for row in rows:
        if isinstance(row, list):
            candles.append(_parse_ohlc(row))
        elif isinstance(row, dict):
            ts = int(row.get("time") or row.get("openTime") or 0)
            candles.append(Candle(
                ts=_from_ms(ts if ts > 10_000_000_000 else ts * 1000),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            ))
    return [c for c in candles if start_ms <= _ms(c.ts) <= end_ms]


async def _resolve_hyperliquid_coin(base: str) -> str:
    mids = await _hyperliquid_mids()
    if base in mids:
        return base
    kcoin = f"k{base}"
    if kcoin in mids:
        return kcoin
    return base


async def _fetch_hyperliquid_candles(base: str, start_ms: int, end_ms: int) -> list[Candle]:
    coin = await _resolve_hyperliquid_coin(base)
    data = await _post_json(
        "https://api.hyperliquid.xyz/info",
        {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": "1m",
                "startTime": start_ms,
                "endTime": end_ms,
            },
        },
    )
    if not isinstance(data, list):
        return []
    candles = []
    for row in data:
        ts = int(row["t"])
        candles.append(Candle(
            ts=_from_ms(ts),
            open=float(row["o"]),
            high=float(row["h"]),
            low=float(row["l"]),
            close=float(row["c"]),
        ))
    return sorted(candles, key=lambda c: c.ts)


async def _fetch_candles_batch(
    exchange: str, symbol: str, since: datetime, until: datetime,
) -> list[Candle]:
    exchange = normalize_exchange(exchange)
    pair = _normalize_pair(symbol)
    base = _base_symbol(symbol)
    start_ms = _ms(since)
    end_ms = _ms(until)

    if exchange == "BINANCE":
        return await _fetch_binance_candles(pair, start_ms, end_ms)
    if exchange == "OKX":
        return await _fetch_okx_candles(base, start_ms, end_ms)
    if exchange == "BYBIT":
        return await _fetch_bybit_candles(pair, start_ms, end_ms)
    if exchange == "BITGET":
        return await _fetch_bitget_candles(pair, start_ms, end_ms)
    if exchange == "MEXC":
        return await _fetch_mexc_candles(base, start_ms, end_ms)
    if exchange == "BINGX":
        return await _fetch_bingx_candles(pair, start_ms, end_ms)
    if exchange == "HYPERLIQUID":
        return await _fetch_hyperliquid_candles(base, start_ms, end_ms)
    return []


async def fetch_candles(
    exchange: str,
    symbol: str,
    since: datetime,
    until: datetime | None = None,
) -> list[Candle]:
    """1m OHLC candles from ``since`` to ``until`` (paginated)."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    until = until or datetime.now(timezone.utc)
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if since >= until:
        return []

    all_candles: dict[int, Candle] = {}
    cursor = since - timedelta(minutes=1)
    max_pages = 200

    for _ in range(max_pages):
        batch = await _fetch_candles_batch(exchange, symbol, cursor, until)
        if not batch:
            break
        for c in batch:
            if since <= c.ts <= until:
                all_candles[_ms(c.ts)] = c
        last = batch[-1].ts
        if last >= until - timedelta(minutes=1):
            break
        next_cursor = last + timedelta(minutes=1)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 50:
            break

    return sorted(all_candles.values(), key=lambda c: c.ts)


async def fetch_price(exchange: str, symbol: str) -> float | None:
    exchange = normalize_exchange(exchange)
    pair = _normalize_pair(symbol)
    base = _base_symbol(symbol)

    if exchange == "HYPERLIQUID":
        return await _fetch_hyperliquid(symbol)

    if exchange == "MEXC":
        return await _fetch_mexc(symbol)

    if exchange == "OKX":
        for inst in (f"{base}-USDT-SWAP", f"{base}-USDT"):
            data = await _get_json(
                f"https://www.okx.com/api/v5/market/ticker?instId={inst}"
            )
            if data and data.get("data"):
                return float(data["data"][0]["last"])

    if exchange == "BINANCE":
        data = await _get_json(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={pair}"
        )
        if data:
            return float(data["price"])
        data = await _get_json(
            f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        )
        if data:
            return float(data["price"])

    if exchange == "BYBIT":
        data = await _get_json(
            f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={pair}"
        )
        items = (data or {}).get("result", {}).get("list", [])
        if items:
            return float(items[0]["lastPrice"])

    if exchange == "BITGET":
        data = await _get_json(
            f"https://api.bitget.com/api/v2/mix/market/ticker"
            f"?symbol={pair}&productType=USDT-FUTURES"
        )
        if data and data.get("data"):
            d = data["data"]
            if isinstance(d, list) and d:
                return float(d[0]["lastPr"])
            if isinstance(d, dict):
                return float(d["lastPr"])

    if exchange == "BINGX":
        data = await _get_json(
            f"https://open-api.bingx.com/openApi/swap/v2/quote/price?symbol={_bingx_symbol(pair)}"
        )
        if data and data.get("data"):
            return float(data["data"]["price"])

    return None
