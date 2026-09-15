"""OKX candle pagination must return history for downtime replay."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from bot.services.price_service import _fetch_okx_candles, _ms


def _okx_row(ts_ms: int, high: float) -> list:
    return [str(ts_ms), "78000", str(high), "77900", "78050", "1", "1", "1", "1"]


@pytest.mark.asyncio
async def test_okx_candles_paginates_and_filters_range():
    start = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc)
    start_ms = _ms(start)
    end_ms = _ms(end)

    page1_ts = end_ms - 30 * 60_000
    page2_ts = start_ms + 5 * 60_000

    async def fake_get(url: str):
        if "after=" not in url:
            return None
        after = int(url.split("after=")[1].split("&")[0])
        if after > end_ms:
            return {"data": [_okx_row(page1_ts, 79768.0), _okx_row(end_ms - 60_000, 79500.0)]}
        if after == page1_ts:
            return {"data": [_okx_row(page2_ts, 79300.0)]}
        return {"data": []}

    with patch("bot.services.price_service._get_json", new=AsyncMock(side_effect=fake_get)):
        candles = await _fetch_okx_candles("BTC", start_ms, end_ms)

    assert len(candles) == 3
    assert max(c.high for c in candles) == 79768.0
    assert all(start <= c.ts <= end for c in candles)
