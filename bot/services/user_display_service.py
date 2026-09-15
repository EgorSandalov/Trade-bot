from bot.abstractions.repositories import IProfileRepository, ITradeRepository


class UserDisplayService:
    """Resolves trader display name — single responsibility."""

    def __init__(
        self,
        profile_repo: IProfileRepository,
        trade_repo: ITradeRepository,
    ) -> None:
        self._profile_repo = profile_repo
        self._trade_repo = trade_repo

    async def resolve(self, user_id: int) -> tuple[str, str | None]:
        profile = await self._profile_repo.get_profile(user_id)
        if profile and profile.display_name:
            return profile.display_name, profile.username
        trades = await self._trade_repo.list_user_trades(user_id, limit=1)
        if trades:
            return trades[0].user_name, trades[0].username
        return "Trader", None
