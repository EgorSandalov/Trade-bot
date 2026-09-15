"""Repository abstractions (Dependency Inversion — depend on interfaces, not SQLite)."""

from __future__ import annotations

from typing import Protocol

from bot.domain.enums import Period, TradeEventType
from bot.domain.models import LeaderboardEntry, Trade, TraderStats


class ITradeRepository(Protocol):
    async def create(self, trade: Trade) -> Trade: ...

    async def get_by_id(self, trade_id: int) -> Trade | None: ...

    async def update(self, trade: Trade) -> None: ...

    async def add_event(
        self,
        trade_id: int,
        event_type: TradeEventType,
        description: str,
        *,
        at: object = None,
    ) -> None: ...

    async def replace_sl(self, trade_id: int, stop_loss) -> None: ...

    async def replace_tps(self, trade_id: int, take_profits) -> None: ...

    async def get_partial_exits(self, trade_id: int) -> list[tuple[float, float]]: ...

    async def list_open_trades(self) -> list[Trade]: ...

    async def list_user_trades(self, user_id: int, *, limit: int | None = None) -> list[Trade]: ...

    async def list_user_trades_for_period(self, user_id: int, period: Period) -> list[Trade]: ...

    async def get_events(self, trade_id: int) -> list: ...


class IProfileRepository(Protocol):
    async def get_profile(self, user_id: int): ...

    async def save_banner(
        self,
        user_id: int,
        profile_type: str,
        photo_path: str | None,
        telegram_file_id: str | None,
        *,
        display_name: str | None = None,
        username: str | None = None,
    ) -> None: ...

    async def save_reaction_sticker(
        self,
        user_id: int,
        file_id: str,
        *,
        kind: str = "sticker",
        display_name: str | None = None,
        username: str | None = None,
    ) -> None: ...

    async def save_loss_reaction_sticker(
        self,
        user_id: int,
        file_id: str,
        *,
        kind: str = "sticker",
        display_name: str | None = None,
        username: str | None = None,
    ) -> None: ...


class IStatsRepository(Protocol):
    async def get_trader_stats(self, user_id: int, period: Period) -> TraderStats | None: ...

    async def get_leaderboard(self, period: Period) -> list[LeaderboardEntry]: ...

    async def get_trader_closed_trades(self, user_id: int, period: Period) -> list[Trade]: ...
