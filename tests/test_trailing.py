import pytest

from bot.domain.enums import EntryType, Side, TradeStatus, TrailMode
from bot.domain.results import Failure, Success
from bot.domain.exchange_trailing import validate_trailing_for_exchange
from bot.domain.models import ParsedStopLoss, StopLoss, Trade
from bot.domain.trailing import (
    apply_trailing_to_candle,
    compute_sl_from_extreme,
    initial_trailing_state,
    parse_sl_line,
    sl_is_live,
)


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=1,
        user_id=1,
        user_name="T",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.OPEN,
        entry_price=100000.0,
        executed_entry_price=100000.0,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def test_parse_trailing_percent():
    r = parse_sl_line("OKX", "SL: trail 3%", Side.LONG)
    assert isinstance(r, Success)
    assert r.value.trail_mode == TrailMode.PERCENT
    assert r.value.trail_value == 3


def test_parse_trailing_decimal_comma_percent():
    r = parse_sl_line("OKX", "SL: trail 0,5%", Side.LONG)
    assert isinstance(r, Success)
    assert r.value.trail_value == pytest.approx(0.5)


@pytest.mark.parametrize(
    "line",
    [
        "SL: trail 500 - 96000 stop 79000",
        "SL: trail 500 96000 stop 79000",
        "SL: trail 500, 96000 stop 79000",
        "SL: trail 3% - 96000 stop 79000",
        "SL: trail 3% 96000 stop 79000",
        "SL: trail 500 @ 96000 stop 79000",  # legacy
    ],
)
def test_parse_trailing_with_activation_separators(line):
    r = parse_sl_line("OKX", line, Side.LONG)
    assert isinstance(r, Success)
    assert r.value.activation_price == 96000
    assert r.value.pre_activation_stop == 79000
    if "3%" in line:
        assert r.value.trail_mode == TrailMode.PERCENT
        assert r.value.trail_value == 3
    else:
        assert r.value.trail_mode == TrailMode.DISTANCE
        assert r.value.trail_value == 500


def test_hyperliquid_rejects_trailing():
    r = parse_sl_line("HYPERLIQUID", "SL: trail 3%", Side.LONG)
    assert isinstance(r, Failure)


def test_binance_rejects_fixed_distance():
    err = validate_trailing_for_exchange("BINANCE", TrailMode.DISTANCE, has_activation=False)
    assert err is not None


def test_compute_sl_long_percent():
    assert compute_sl_from_extreme(Side.LONG, 120000, TrailMode.PERCENT, 3) == pytest.approx(116400)


def test_trailing_long_ratchet_up_only():
    trade = _trade(
        stop_loss=StopLoss(
            id=1, trade_id=1,
            price=116400,
            trail_mode=TrailMode.PERCENT,
            trail_value=3,
            extreme_price=120000,
            trail_active=True,
        ),
    )
    _, changed = apply_trailing_to_candle(trade, high=125000, low=124000)
    assert changed
    assert trade.stop_loss.price == pytest.approx(121250)
    assert trade.stop_loss.extreme_price == 125000


def test_trailing_does_not_lower_sl_on_pullback():
    trade = _trade(
        stop_loss=StopLoss(
            id=1, trade_id=1,
            price=121250,
            trail_mode=TrailMode.PERCENT,
            trail_value=3,
            extreme_price=125000,
            trail_active=True,
        ),
    )
    _, changed = apply_trailing_to_candle(trade, high=123000, low=122000)
    assert not changed
    assert trade.stop_loss.price == pytest.approx(121250)


def test_activation_gates_sl():
    sl = initial_trailing_state(
        ParsedStopLoss(trail_mode=TrailMode.PERCENT, trail_value=3, activation_price=96000),
        Side.LONG,
        90000,
    )
    assert not sl.trail_active
    assert not sl_is_live(sl)


def test_candle_replay_triggers_trailed_sl():
    from bot.domain.candles import next_trigger_in_candle
    from bot.domain.models import TakeProfitLevel
    from bot.domain.candles import Candle
    from datetime import datetime, timezone

    trade = _trade(
        stop_loss=StopLoss(
            id=1, trade_id=1,
            price=121250,
            trail_mode=TrailMode.PERCENT,
            trail_value=3,
            extreme_price=125000,
            trail_active=True,
        ),
        take_profits=[
            TakeProfitLevel(id=1, trade_id=1, order_index=1, price=130000.0, close_percent=100.0),
        ],
    )
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        open=122000.0,
        high=122500.0,
        low=121000.0,
        close=121500.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.kind.value == "sl"


def test_short_trailing_moves_sl_down():
    trade = _trade(
        side=Side.SHORT,
        stop_loss=StopLoss(
            id=1, trade_id=1,
            price=82400,
            trail_mode=TrailMode.PERCENT,
            trail_value=3,
            extreme_price=80000,
            trail_active=True,
        ),
    )
    _, changed = apply_trailing_to_candle(trade, high=76000, low=75000)
    assert changed
    assert trade.stop_loss.price == pytest.approx(77250)
    assert trade.stop_loss.extreme_price == 75000
