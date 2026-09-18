from datetime import datetime, timezone

import pytest

from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus, TrailMode
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.domain.parser import parse_trade_message
from bot.domain.trade_edit import validate_trade_edit
from bot.utils.trade_setup import format_trade_setup, split_edit_message


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=1,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.LIMIT,
        status=TradeStatus.OPEN,
        entry_price=95000.0,
        executed_entry_price=95000.0,
        remaining_percent=100.0,
        stop_loss=StopLoss(id=1, trade_id=1, price=93000.0),
        take_profits=[
            TakeProfitLevel(id=1, trade_id=1, order_index=1, price=96000.0, close_percent=50.0),
            TakeProfitLevel(id=2, trade_id=1, order_index=2, price=97000.0, close_percent=50.0),
        ],
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


SETUP = """\
OKX
BTC
LONG
Type: limit
Leverage: 10
Entry: 95000
SL: 93000
TP1: 96000 - 50%
TP2: 97000 - 50%
Comment: test
"""


def test_format_trade_setup_roundtrip():
    text = format_trade_setup(_trade())
    assert "OKX" in text
    assert "Entry: 95000" in text
    assert "TP1: 96000 - 50%" in text


def test_split_edit_reason():
    body, reason = split_edit_message(SETUP + "\nReason: moved SL to BE")
    assert "Reason:" not in body
    assert reason == "moved SL to BE"


def test_validate_rejects_sl_above_market_for_long():
    """SL above current price is invalid even if it was valid vs entry."""
    bad = SETUP.replace("SL: 93000", "SL: 80000")
    _, _, errors = validate_trade_edit(_trade(), bad, 79500.0)
    assert any("would trigger immediately" in e for e in errors)


def test_validate_allows_breakeven_sl_above_entry_for_partial_long():
    """Partially closed LONG: SL above Entry but below market is allowed."""
    trade = _trade(
        status=TradeStatus.PARTIALLY_CLOSED,
        remaining_percent=70.0,
        entry_type=EntryType.LIMIT,
        entry_price=77000.0,
        executed_entry_price=77000.0,
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=1, order_index=1, price=77100.0,
                close_percent=30.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=1, order_index=2, price=77400.0, close_percent=70.0,
            ),
        ],
    )
    edit = """\
OKX
BTC
LONG
Type: limit
Leverage: 10
Entry: 77000
SL: 77200
TP2: 77400 - 70%
"""
    parsed = parse_trade_message(edit)
    assert not hasattr(parsed, "error")
    _, _, errors = validate_trade_edit(trade, edit, 77338.0)
    assert errors == []


def test_validate_allows_trailing_sl_above_entry_for_long():
    """LONG in profit: SL above entry but below market is allowed."""
    trade = _trade(
        entry_type=EntryType.MARKET,
        entry_price=78600.0,
        executed_entry_price=78600.0,
        stop_loss=StopLoss(id=1, trade_id=1, price=78000.0),
        take_profits=[
            TakeProfitLevel(id=1, trade_id=1, order_index=1, price=79800.0, close_percent=50.0),
            TakeProfitLevel(id=2, trade_id=1, order_index=2, price=80500.0, close_percent=50.0),
        ],
    )
    edit = """\
OKX
BTC
LONG
Type: market
Leverage: 10
SL: 79000
TP1: 79800 - 50%
TP2: 80500 - 50%
"""
    _, _, errors = validate_trade_edit(trade, edit, 79400.0)
    assert errors == []


def test_validate_allows_trailing_sl_below_entry_for_short():
    """SHORT in profit: SL below entry but above market is allowed."""
    trade = _trade(
        side=Side.SHORT,
        entry_type=EntryType.MARKET,
        entry_price=78600.0,
        executed_entry_price=78600.0,
        stop_loss=StopLoss(id=1, trade_id=1, price=79200.0),
        take_profits=[
            TakeProfitLevel(id=1, trade_id=1, order_index=1, price=77000.0, close_percent=100.0),
        ],
    )
    edit = """\
OKX
BTC
SHORT
Type: market
Leverage: 10
SL: 78800
TP1: 77000 - 100%
"""
    _, _, errors = validate_trade_edit(trade, edit, 78500.0)
    assert errors == []


def test_validate_rejects_tp_sum_over_remaining():
    trade = _trade(
        status=TradeStatus.PARTIALLY_CLOSED,
        remaining_percent=60.0,
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=1, order_index=1, price=96000.0,
                close_percent=40.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=1, order_index=2, price=97000.0, close_percent=60.0,
            ),
        ],
    )
    edit = """\
OKX
BTC
LONG
Type: limit
Leverage: 10
Entry: 95000
SL: 93000
TP2: 98000 - 40%
TP3: 99000 - 30%
"""
    _, _, errors = validate_trade_edit(trade, edit, 96500.0)
    assert any("only 60%" in e for e in errors)


def test_validate_rejects_readding_hit_tp():
    trade = _trade(
        status=TradeStatus.PARTIALLY_CLOSED,
        remaining_percent=50.0,
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=1, order_index=1, price=96000.0,
                close_percent=50.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=1, order_index=2, price=97000.0, close_percent=50.0,
            ),
        ],
    )
    edit = SETUP  # includes TP1 again
    _, _, errors = validate_trade_edit(trade, edit, 96500.0)
    assert any("TP1 already hit" in e for e in errors)


def test_validate_rejects_tp_below_market_for_long():
    trade = _trade(
        status=TradeStatus.PARTIALLY_CLOSED,
        remaining_percent=50.0,
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=1, order_index=1, price=96000.0,
                close_percent=50.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=1, order_index=2, price=97000.0, close_percent=50.0,
            ),
        ],
    )
    edit = """\
OKX
BTC
LONG
Type: limit
Leverage: 10
Entry: 95000
SL: 93000
TP2: 96000 - 50%
"""
    _, _, errors = validate_trade_edit(trade, edit, 96500.0)
    assert any("already reachable" in e for e in errors)


def test_validate_allows_pre_activation_sl_for_short_trailing():
    trade = _trade(
        exchange="OKX",
        symbol="HYPEUSDT",
        side=Side.SHORT,
        entry_type=EntryType.MARKET,
        entry_price=90.633,
        executed_entry_price=90.633,
        stop_loss=StopLoss(
            id=1,
            trade_id=1,
            price=88.5,
            trail_mode=TrailMode.DISTANCE,
            trail_value=0.5,
            activation_price=88.0,
            pre_activation_stop=93.13,
            trail_active=False,
        ),
        take_profits=[
            TakeProfitLevel(id=1, trade_id=1, order_index=1, price=85.0, close_percent=100.0),
        ],
    )
    edit = """\
OKX
HYPE
SHORT
Type: market
Leverage: 10
SL: 95.7
SL: trail 0.5 - 88
TP1: 85 - 100%
"""
    _, _, errors = validate_trade_edit(trade, edit, 91.638)
    assert errors == []


def test_validate_uses_active_trailing_sl_when_activation_reached():
    trade = _trade(
        side=Side.LONG,
        entry_type=EntryType.MARKET,
        entry_price=80000.0,
        executed_entry_price=80000.0,
        stop_loss=StopLoss(
            id=1,
            trade_id=1,
            price=81200.0,
            trail_mode=TrailMode.DISTANCE,
            trail_value=420.0,
            activation_price=81700.0,
            pre_activation_stop=79000.0,
            trail_active=True,
            extreme_price=81600.0,
        ),
        take_profits=[
            TakeProfitLevel(id=1, trade_id=1, order_index=1, price=82413.0, close_percent=100.0),
        ],
    )
    edit = """\
OKX
BTC
LONG
Type: market
Leverage: 10
SL: 79000
SL: trail 420 - 81700
TP1: 82413 - 100%
"""
    _, _, errors = validate_trade_edit(trade, edit, 81600.0)
    assert errors == []


def test_validate_accepts_valid_partial_edit():
    trade = _trade(
        status=TradeStatus.PARTIALLY_CLOSED,
        remaining_percent=50.0,
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=1, order_index=1, price=96000.0,
                close_percent=50.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=1, order_index=2, price=97000.0, close_percent=50.0,
            ),
        ],
    )
    edit = """\
OKX
BTC
LONG
Type: limit
Leverage: 10
Entry: 95000
SL: 94000
TP2: 98000 - 50%
Reason: trail SL
"""
    parsed, reason, errors = validate_trade_edit(trade, edit, 96500.0)
    assert not errors
    assert parsed is not None
    assert reason == "trail SL"
