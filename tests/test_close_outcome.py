from datetime import datetime, timezone

from bot.domain.enums import (
    CloseReason,
    EntryType,
    LevelStatus,
    Side,
    TradeEventType,
    TradeStatus,
)
from bot.domain.models import TakeProfitLevel, Trade, TradeEvent
from bot.utils.formatters import _close_outcome_label, format_close_result


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=5,
        user_id=1,
        user_name="T",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.CLOSED,
        entry_price=78600.0,
        executed_entry_price=78600.0,
        close_reason=CloseReason.BREAKEVEN,
        result_clean_move_pct=0.30,
        result_personal_move_pct=3.0,
        result_points=0.45,
        take_profits=[
            TakeProfitLevel(
                None, 5, 1, 79200.0, 50.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                None, 5, 2, 79500.0, 50.0, status=LevelStatus.PENDING,
            ),
        ],
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def test_tp1_then_sl_outcome():
    events = [
        TradeEvent(
            None, 5, TradeEventType.TP_TRIGGERED,
            "TP1: $79,200.00, close 50%, remaining 50%",
            datetime(2026, 9, 9, 11, 42, tzinfo=timezone.utc),
        ),
        TradeEvent(
            None, 5, TradeEventType.SL_TRIGGERED,
            "SL: $78,600.00, close 50% remaining",
            datetime(2026, 9, 9, 13, 15, tzinfo=timezone.utc),
        ),
    ]
    label = _close_outcome_label(_trade(), events)
    assert label == "🎯 TP1 → ✅ Stop (profit) · Breakeven"


def test_all_tp_outcome():
    trade = _trade(
        close_reason=CloseReason.TP,
        take_profits=[
            TakeProfitLevel(None, 5, 1, 79200.0, 50.0, status=LevelStatus.TRIGGERED),
            TakeProfitLevel(None, 5, 2, 79500.0, 50.0, status=LevelStatus.TRIGGERED),
        ],
    )
    events = [
        TradeEvent(None, 5, TradeEventType.TP_TRIGGERED, "TP1: ...", datetime.now(timezone.utc)),
        TradeEvent(None, 5, TradeEventType.TP_TRIGGERED, "TP2: ...", datetime.now(timezone.utc)),
    ]
    assert _close_outcome_label(trade, events) == "🎯 All TP"


def test_format_close_result_includes_path():
    events = [
        TradeEvent(
            None, 6, TradeEventType.TP_TRIGGERED, "TP1: $79,500.00, close 50%",
            datetime(2026, 9, 9, 13, 15, tzinfo=timezone.utc),
        ),
        TradeEvent(
            None, 6, TradeEventType.SL_TRIGGERED, "SL: $79,400.00, close 50%",
            datetime(2026, 9, 9, 13, 21, tzinfo=timezone.utc),
        ),
    ]
    trade = _trade(
        id=6,
        user_trade_number=6,
        close_reason=CloseReason.BREAKEVEN,
        result_clean_move_pct=0.14,
        result_personal_move_pct=1.4,
        result_points=-1.0,
    )
    text = format_close_result(trade, events)
    assert "TP1 →" in text
    assert "Breakeven" in text


def test_profitable_trailing_sl_close_label():
    from bot.domain.enums import TrailMode
    from bot.domain.models import StopLoss

    trade = _trade(
        close_reason=CloseReason.SL,
        result_clean_move_pct=0.33,
        result_personal_move_pct=3.3,
        result_points=0.49,
        stop_loss=StopLoss(None, 8, 77090.0, trail_mode=TrailMode.DISTANCE, trail_value=300.0),
    )
    events = [
        TradeEvent(
            None, 8, TradeEventType.SL_TRAILED,
            "Trailing SL: $76,570.60 → $77,090.00 (ext $77,390.00)",
            datetime(2026, 9, 13, 18, 58, 4, tzinfo=timezone.utc),
        ),
        TradeEvent(
            None, 8, TradeEventType.SL_TRIGGERED,
            "SL: $77,090.00, close 100% remaining",
            datetime(2026, 9, 14, 13, 31, tzinfo=timezone.utc),
        ),
    ]
    assert _close_outcome_label(trade, events) == "📈 Trailing stop"
