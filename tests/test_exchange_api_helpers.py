from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from bot.domain.candles import Candle
from bot.services.price_service import (
    _bingx_symbol,
    _chunk_end_ms,
    _fetch_bybit_candles,
    _fetch_hyperliquid_candles,
    _ms,
    fetch_candles,
    fetch_price,
)


def test_bingx_symbol_format():
    assert _bingx_symbol("BTCUSDT") == "BTC-USDT"
    assert _bingx_symbol("BTC/USDT") == "BTC-USDT"


def test_chunk_end_ms_caps_window():
    start = 1_000_000
    end = start + 2000 * 60_000
    assert _chunk_end_ms(start, end) == start + 999 * 60_000


@pytest.mark.asyncio
async def test_bybit_candles_request_uses_chunked_end():
    start_ms = 1_000_000
    end_ms = start_ms + 5 * 60 * 60_000
    seen_urls: list[str] = []

    async def fake_get(url: str):
        seen_urls.append(url)
        return {"result": {"list": []}}

    with patch("bot.services.price_service._get_json", new=AsyncMock(side_effect=fake_get)):
        await _fetch_bybit_candles("BTCUSDT", start_ms, end_ms)

    assert seen_urls
    assert f"end={_chunk_end_ms(start_ms, end_ms)}" in seen_urls[0]


@pytest.mark.asyncio
async def test_fetch_candles_paginates_bybit_in_two_batches():
    since = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    until = since + timedelta(hours=20)
    t2 = _ms(since + timedelta(hours=18))

    def _candle(ts_ms: int) -> Candle:
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return Candle(ts=ts, open=1.0, high=1.0, low=1.0, close=1.0)

    async def fake_batch(exchange, symbol, batch_since, batch_until):
        if batch_since <= since + timedelta(minutes=1):
            return [
                _candle(_ms(since + timedelta(minutes=i)))
                for i in range(60)
            ]
        return [_candle(t2)]

    mock_batch = AsyncMock(side_effect=fake_batch)
    with patch("bot.services.price_service._fetch_candles_batch", mock_batch):
        candles = await fetch_candles("BYBIT", "BTCUSDT", since, until)

    assert len(candles) == 61
    assert mock_batch.await_count >= 2


@pytest.mark.asyncio
async def test_bingx_fetch_price_uses_dashed_symbol():
    async def fake_get(url: str):
        if "BTC-USDT" in url:
            return {"data": {"price": "70000"}}
        return None

    with patch("bot.services.price_service._get_json", new=AsyncMock(side_effect=fake_get)):
        price = await fetch_price("BINGX", "BTCUSDT")

    assert price == 70000.0


@pytest.mark.asyncio
async def test_hyperliquid_candles_use_k_prefix_coin():
    posted: list[dict] = []

    async def fake_mids():
        return {"kPEPE": 0.003}

    async def fake_post(url: str, payload: dict):
        posted.append(payload)
        return []

    with patch("bot.services.price_service._hyperliquid_mids", new=AsyncMock(side_effect=fake_mids)):
        with patch("bot.services.price_service._post_json", new=AsyncMock(side_effect=fake_post)):
            await _fetch_hyperliquid_candles("PEPE", 1_000_000, 2_000_000)

    assert posted[0]["req"]["coin"] == "kPEPE"
