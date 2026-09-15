import pytest

from bot.domain.calculations import (
    calc_trade_points,
    clean_move_pct,
    is_breakeven_close,
    personal_move_pct,
    trade_result_clean_move,
    weighted_avg_exit,
)
from bot.domain.enums import EntryType, Side, TrailMode
from bot.domain.parser import parse_trade_message
from bot.domain.results import Failure, Success

SAMPLE_LIMIT = """OKX
BTC
LONG
Type: limit
Leverage: 10
Entry: 110000
SL: 108000
TP1: 112000 - 25%
TP2: 115000 - 25%
TP3: 120000 - 50%"""

SAMPLE_MARKET = """OKX
BTC
LONG
Type: market
Leverage: 10
SL: 108000
TP1: 112000 - 100%"""

SAMPLE_OPEN = """OKX
BTC
SHORT
Type: open
Leverage: 5
Entry: 95000
SL: 96000
TP1: 93000 - 100%"""


def test_parse_limit():
    result = parse_trade_message(SAMPLE_LIMIT)
    assert isinstance(result, Success)
    assert result.value.leverage == 10
    assert result.value.entry_type == EntryType.LIMIT
    assert result.value.entry_price == 110000


def test_parse_market_no_entry():
    result = parse_trade_message(SAMPLE_MARKET)
    assert isinstance(result, Success)
    assert result.value.entry_type == EntryType.MARKET
    assert result.value.entry_price is None


def test_parse_open():
    result = parse_trade_message(SAMPLE_OPEN)
    assert isinstance(result, Success)
    assert result.value.entry_type == EntryType.OPEN


def test_market_rejects_entry():
    msg = SAMPLE_MARKET.replace("SL:", "Entry: 110000\nSL:")
    result = parse_trade_message(msg)
    assert isinstance(result, Failure)


def test_leverage_must_be_at_least_one():
    for bad in ("Leverage: -5", "Leverage: 0"):
        msg = SAMPLE_LIMIT.replace("Leverage: 10", bad)
        result = parse_trade_message(msg)
        assert isinstance(result, Failure), bad


def test_normalize_leverage():
    from bot.domain.calculations import normalize_leverage, personal_move_pct

    assert normalize_leverage(-10) == 10
    assert normalize_leverage(200) == 200
    assert personal_move_pct(-8.16, -10) == pytest.approx(-81.6)


def test_points_formula():
    assert calc_trade_points(1.0, 50.0) == pytest.approx(3.5)
    assert calc_trade_points(0.5, 5.0) == pytest.approx(0.75)  # 0.5% clean, 10x
    assert calc_trade_points(0.5, 0.5) == pytest.approx(0.53)
    assert calc_trade_points(-1.0, -50.0) == pytest.approx(-3.5)  # small loss: −1 + personal/20
    assert calc_trade_points(-5.0, -250.0) == pytest.approx(-17.5)


def test_breakeven_zone():
    assert is_breakeven_close(0.0) is True
    assert is_breakeven_close(0.2) is True
    assert is_breakeven_close(0.21) is False
    assert is_breakeven_close(-0.1) is False
    assert calc_trade_points(0.1, 1.0) == -1.0
    assert calc_trade_points(0.0, 0.0, force_bu=True) == -1.0


def test_small_loss_minus_one_plus_personal():
    personal = personal_move_pct(-0.3, 10)
    assert personal == pytest.approx(-3.0)
    assert calc_trade_points(-0.3, personal) == pytest.approx(-1.15)

    assert calc_trade_points(-0.5, personal_move_pct(-0.5, 10)) == pytest.approx(-1.25)
    assert calc_trade_points(-1.0, personal_move_pct(-1.0, 50)) == pytest.approx(-3.5)

    # 200x hurts in small-loss zone
    assert calc_trade_points(-0.5, personal_move_pct(-0.5, 200)) == pytest.approx(-6.0)


def test_below_minus_one_uses_formula():
    assert calc_trade_points(-1.01, personal_move_pct(-1.01, 10)) == pytest.approx(-1.52)
    assert calc_trade_points(-2.0, personal_move_pct(-2.0, 10)) == pytest.approx(-3.0)


def test_clean_move():
    assert clean_move_pct(100, 110, Side.LONG) == pytest.approx(10)
    assert personal_move_pct(10, 10) == pytest.approx(100)
    assert personal_move_pct(-8.16, 10) == pytest.approx(-81.6)


def test_weighted_result_tp1_then_sl():
    """50% at TP1 (+1.25%), 50% at SL (−1.25%) → net 0% clean on full position."""
    entry = 80000.0
    exits = [
        (81000.0, 0.5),
        (79000.0, 0.5),
    ]
    clean = trade_result_clean_move(entry, Side.LONG, exits)
    assert clean == pytest.approx(0.0)
    assert weighted_avg_exit(exits) == pytest.approx(80000.0)


def test_parse_tp_separators():
    for tp_line in (
        "TP1: 112000 - 50%",
        "TP1: 112000 50%",
        "TP1: 112000, 50%",
        "TP1: 112000 — 50%",
        "TP1: 112000 - 33,5%",
    ):
        msg = SAMPLE_LIMIT.rsplit("TP1:", 1)[0] + tp_line + "\nTP2: 115000 - 50%"
        result = parse_trade_message(msg)
        assert isinstance(result, Success), tp_line
        if "33,5" in tp_line:
            assert result.value.take_profits[0] == (112000.0, 33.5)
        else:
            assert result.value.take_profits[0] == (112000.0, 50.0)


def test_trailing_activation_requires_fixed_sl():
    msg = """OKX
BTC
LONG
Type: market
Leverage: 10
SL: trail 0,5% - 80000
TP1: 85000 - 100%"""
    result = parse_trade_message(msg)
    assert isinstance(result, Failure)


def test_parse_dual_sl_fixed_then_trailing():
    msg = """OKX
BTC
LONG
Type: market
Leverage: 10
SL: 75000
SL: trail 0,5% - 80000
TP1: 85000 - 100%"""
    result = parse_trade_message(msg)
    assert isinstance(result, Success)
    sl = result.value.stop_loss
    assert sl.trail_mode == TrailMode.PERCENT
    assert sl.trail_value == pytest.approx(0.5)
    assert sl.activation_price == 80000
    assert sl.pre_activation_stop == 75000
