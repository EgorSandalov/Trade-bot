from dataclasses import dataclass, field
from datetime import datetime

from bot.domain.enums import (
    CloseReason,
    EntryType,
    LevelStatus,
    Side,
    TradeEventType,
    TradeStatus,
    TrailMode,
)


@dataclass
class TakeProfitLevel:
    id: int | None
    trade_id: int | None
    order_index: int
    price: float
    close_percent: float
    status: LevelStatus = LevelStatus.PENDING
    executed_price: float | None = None
    executed_at: datetime | None = None


@dataclass
class ParsedStopLoss:
    trail_mode: TrailMode = TrailMode.FIXED
    price: float = 0.0
    trail_value: float | None = None
    activation_price: float | None = None
    pre_activation_stop: float | None = None


@dataclass
class StopLoss:
    id: int | None
    trade_id: int | None
    price: float
    status: LevelStatus = LevelStatus.PENDING
    executed_price: float | None = None
    executed_at: datetime | None = None
    trail_mode: TrailMode = TrailMode.FIXED
    trail_value: float | None = None
    activation_price: float | None = None
    pre_activation_stop: float | None = None
    extreme_price: float | None = None
    trail_active: bool = False


@dataclass
class TradeEvent:
    id: int | None
    trade_id: int
    event_type: TradeEventType
    description: str
    created_at: datetime


@dataclass
class Trade:
    id: int | None
    user_id: int
    user_name: str
    username: str | None
    exchange: str
    symbol: str
    side: Side
    leverage: int
    entry_type: EntryType
    status: TradeStatus
    entry_price: float
    executed_entry_price: float | None
    remaining_percent: float = 100.0
    stop_loss: StopLoss | None = None
    take_profits: list[TakeProfitLevel] = field(default_factory=list)
    comment: str | None = None
    close_reason: CloseReason | None = None
    result_clean_move_pct: float | None = None
    result_personal_move_pct: float | None = None
    avg_exit_price: float | None = None
    card_message_id: int | None = None
    card_chat_id: int | None = None
    setup_chat_id: int | None = None
    setup_message_id: int | None = None
    setup_thread_id: int | None = None
    result_points: float | None = None
    user_trade_number: int | None = None
    last_monitored_at: datetime | None = None
    created_at: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    events: list[TradeEvent] = field(default_factory=list)

    @property
    def effective_entry(self) -> float:
        return self.executed_entry_price or self.entry_price

    @property
    def display_number(self) -> int:
        """Per-user trade serial shown in UI."""
        return self.user_trade_number or self.id or 0

    @property
    def pair_label(self) -> str:
        return f"{self.symbol} {self.side.value.upper()} — {self.exchange.upper()}"


@dataclass
class ParsedTrade:
    exchange: str
    symbol: str
    side: Side
    leverage: int
    entry_price: float | None
    entry_type: EntryType
    stop_loss: ParsedStopLoss
    take_profits: list[tuple[float, float]]
    comment: str | None


@dataclass
class TraderStats:
    user_id: int
    display_name: str
    username: str | None
    trades_count: int
    wins: int
    losses: int
    win_rate: float
    points: float
    total_clean_move_pct: float
    total_personal_move_pct: float
    avg_clean_move_pct: float
    avg_personal_move_pct: float
    avg_win_clean_pct: float | None
    avg_loss_clean_pct: float | None
    avg_win_personal_pct: float | None
    avg_loss_personal_pct: float | None
    best_trade_pct: float | None
    worst_trade_pct: float | None


@dataclass
class LeaderboardEntry:
    rank: int
    user_id: int
    display_name: str
    username: str | None
    trades_count: int
    points: float
    total_clean_move_pct: float
    total_personal_move_pct: float
    win_rate: float
    profile_only: bool = False
