from datetime import datetime, timezone

from bot.domain.enums import TradeEventType
from bot.domain.models import TradeEvent
from bot.utils.formatters import format_history


def test_format_history_shows_utc_and_footnote():
    events = [
        TradeEvent(
            None, 1, TradeEventType.SL_TRAILED,
            "Trailing SL: $100 → $110",
            datetime(2026, 9, 13, 17, 12, tzinfo=timezone.utc),
        ),
    ]
    text = format_history(events, trade_number=8)
    assert "UTC" in text
    assert "candle/trigger time" in text
    assert "13.09 17:12 UTC" in text
    assert "#8" in text
