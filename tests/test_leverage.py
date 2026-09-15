import pytest

from bot.services.leverage_service import (
    _EXCHANGE_DEFAULT_MAX,
    normalize_leverage_value,
    validate_leverage,
)


def test_normalize_leverage_sign_only():
    assert normalize_leverage_value(-10) == 10
    assert normalize_leverage_value(50) == 50
    assert normalize_leverage_value(200) == 200


@pytest.mark.asyncio
async def test_validate_leverage_rejects_over_max(monkeypatch):
    async def fake_max(exchange, symbol):
        return 50

    monkeypatch.setattr("bot.services.leverage_service.get_max_leverage", fake_max)

    assert await validate_leverage("OKX", "BTC", 0) is not None
    assert await validate_leverage("OKX", "BTC", 51) is not None
    assert "50x" in (await validate_leverage("OKX", "BTC", 51))
    assert await validate_leverage("OKX", "BTC", 50) is None


def test_exchange_defaults_exist():
    for ex in ("BINANCE", "OKX", "BYBIT", "BITGET", "BINGX", "MEXC", "HYPERLIQUID"):
        assert ex in _EXCHANGE_DEFAULT_MAX
