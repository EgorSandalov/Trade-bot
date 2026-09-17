from bot.domain.parser import looks_like_setup

SAMPLE_SETUP = """OKX
BTC
LONG
Type: market
Leverage: 10
SL: 108000
TP1: 112000 - 100%"""


def test_real_setup_detected():
    assert looks_like_setup(SAMPLE_SETUP) is True


def test_general_chat_messages_ignored():
    assert looks_like_setup("https://t.me/momentum/8463\nзамотивирую себя") is False
    assert looks_like_setup("https://youtube.com/shorts/abc\nZEC zcash") is False
    assert looks_like_setup("Я в позе, часть закрою по TP\nостальное в БУ") is False
    assert looks_like_setup("single line only") is False


def test_exchange_plus_two_lines_not_enough():
    assert looks_like_setup("OKX\nBTC") is False


def test_exchange_symbol_side_without_fields():
    assert looks_like_setup("OKX\nBTC\nLONG") is True


def test_exchange_with_leverage_field():
    assert looks_like_setup("OKX\nBTC\nLeverage: 10") is True


def test_okx_mention_in_chat_not_setup():
    assert looks_like_setup("OKX\nобсуждаем рынок\nсегодня") is False
