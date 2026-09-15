from enum import Enum


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class EntryType(str, Enum):
    MARKET = "market"   # Open now at current price
    LIMIT = "limit"     # Pending limit order
    OPEN = "open"       # Already opened at specified price


class TradeStatus(str, Enum):
    PLANNED = "planned"
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CloseReason(str, Enum):
    TP = "tp"
    SL = "sl"
    MANUAL = "manual"
    BREAKEVEN = "breakeven"
    OTHER = "other"


class TrailMode(str, Enum):
    FIXED = "fixed"
    PERCENT = "percent"
    DISTANCE = "distance"


class LevelStatus(str, Enum):
    PENDING = "pending"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"


class TradeEventType(str, Enum):
    CREATED = "created"
    ENTRY_CHANGED = "entry_changed"
    ENTRY_FILLED = "entry_filled"
    SL_CHANGED = "sl_changed"
    SL_TRAILED = "sl_trailed"
    TP_CHANGED = "tp_changed"
    TP_ADDED = "tp_added"
    TP_TRIGGERED = "tp_triggered"
    SL_TRIGGERED = "sl_triggered"
    PARTIAL_CLOSE = "partial_close"
    FULL_CLOSE = "full_close"
    LEVERAGE_CHANGED = "leverage_changed"
    PARAMS_EDITED = "params_edited"
    STATUS_CHANGED = "status_changed"
    CANCELLED = "cancelled"
    SYNC = "sync"


class Period(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


def period_label(period: "Period") -> str:
    return {
        Period.DAY: "Today",
        Period.WEEK: "This week",
        Period.MONTH: "This month",
        Period.ALL: "All time",
    }[period]
