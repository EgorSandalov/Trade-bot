from aiogram.types import InlineKeyboardMarkup

from bot.abstractions.repositories import IStatsRepository, ITradeRepository
from bot.domain.enums import Period, period_label
from bot.keyboards.menus import my_trades_kb, paginate_my_trades
from bot.services.user_display_service import UserDisplayService
from bot.utils.formatters import format_my_trades_header


class TradesViewService:
    """Builds my-trades list views — presentation logic separated from handlers."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        stats_repo: IStatsRepository,
        user_display: UserDisplayService,
    ) -> None:
        self._trade_repo = trade_repo
        self._stats_repo = stats_repo
        self._user_display = user_display

    async def build_my_trades_view(
        self,
        user_id: int,
        period: Period,
        page: int = 0,
        *,
        note: str = "",
    ) -> tuple[str, list, int, InlineKeyboardMarkup]:
        label = period_label(period)
        stats = await self._stats_repo.get_trader_stats(user_id, period)
        items = await self._trade_repo.list_user_trades_for_period(user_id, period)
        display_name, username = await self._user_display.resolve(user_id)
        _, page, total_pages = paginate_my_trades(items, page)
        text = format_my_trades_header(
            display_name=display_name,
            username=username,
            period_label=label,
            stats=stats,
            trades_count=len(items),
            page=page,
            total_pages=total_pages,
        )
        if note:
            text += f"\n\n{note}"
        return text, items, page, my_trades_kb(items, period, page)
