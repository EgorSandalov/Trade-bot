"""Composition root — wires concrete implementations (Lab2 Program.cs equivalent)."""

from __future__ import annotations

from dataclasses import dataclass

from bot.database.profile_repository import ProfileRepository
from bot.database.repository import StatsRepository, TradeRepository
from bot.services.access_service import AccessService
from bot.services.notify_service import NotifyService
from bot.services.profile_service import ProfileService
from bot.services.trade_service import TradeService
from bot.services.trades_view_service import TradesViewService
from bot.services.user_display_service import UserDisplayService


@dataclass(frozen=True)
class AppContainer:
    access: AccessService
    trade_repo: TradeRepository
    profile_repo: ProfileRepository
    stats_repo: StatsRepository
    trades: TradeService
    profiles: ProfileService
    notify: NotifyService
    user_display: UserDisplayService
    trades_view: TradesViewService

    @classmethod
    def create_default(cls) -> AppContainer:
        trade_repo = TradeRepository()
        profile_repo = ProfileRepository()
        stats_repo = StatsRepository()
        access = AccessService()
        profiles = ProfileService(profile_repo)
        trades = TradeService(trade_repo)
        notify = NotifyService(profiles, trade_repo)
        user_display = UserDisplayService(profile_repo, trade_repo)
        trades_view = TradesViewService(trade_repo, stats_repo, user_display)
        return cls(
            access=access,
            trade_repo=trade_repo,
            profile_repo=profile_repo,
            stats_repo=stats_repo,
            trades=trades,
            profiles=profiles,
            notify=notify,
            user_display=user_display,
            trades_view=trades_view,
        )
