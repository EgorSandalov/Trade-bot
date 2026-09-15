from bot.domain.exchanges import is_supported_exchange, normalize_exchange


def test_normalize_hl():
    assert normalize_exchange("HL") == "HYPERLIQUID"
    assert normalize_exchange("hyperliquid") == "HYPERLIQUID"
    assert is_supported_exchange("HL")
    assert is_supported_exchange("MEXC")
    assert not is_supported_exchange("FTX")
