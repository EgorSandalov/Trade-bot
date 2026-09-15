from datetime import datetime, timedelta, timezone

from bot.config import BREAKEVEN_THRESHOLD_PCT
from bot.database.db import get_connection
from bot.domain.calculations import (
    calc_trade_points,
    is_be_for_stats,
    is_breakeven_close,
    personal_move_pct,
    recalc_trade_result,
)
from bot.services.leverage_service import get_max_leverage, normalize_leverage_value
from bot.domain.enums import (
    CloseReason,
    EntryType,
    LevelStatus,
    Period,
    Side,
    TradeEventType,
    TradeStatus,
    TrailMode,
)
from bot.domain.models import LeaderboardEntry, StopLoss, TakeProfitLevel, Trade, TradeEvent, TraderStats


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def _load_stop_loss(row, trade_id: int) -> StopLoss:
    keys = row.keys()
    trail_mode_raw = row["trail_mode"] if "trail_mode" in keys else "fixed"
    return StopLoss(
        id=row["id"],
        trade_id=trade_id,
        price=row["price"],
        status=LevelStatus(row["status"]),
        executed_price=row["executed_price"],
        executed_at=_parse_dt(row["executed_at"]),
        trail_mode=TrailMode(trail_mode_raw),
        trail_value=row["trail_value"] if "trail_value" in keys else None,
        activation_price=row["activation_price"] if "activation_price" in keys else None,
        extreme_price=row["extreme_price"] if "extreme_price" in keys else None,
        trail_active=bool(row["trail_active"]) if "trail_active" in keys else False,
        pre_activation_stop=row["pre_activation_stop"] if "pre_activation_stop" in keys else None,
    )


class TradeRepository:
    async def create(self, trade: Trade) -> Trade:
        async with get_connection() as db:
            row = await (
                await db.execute(
                    "SELECT COALESCE(MAX(user_trade_number), 0) + 1 FROM trades WHERE user_id=?",
                    (trade.user_id,),
                )
            ).fetchone()
            trade.user_trade_number = row[0]

            cur = await db.execute(
                """
                INSERT INTO trades (
                    user_id, user_name, username, exchange, symbol, side,
                    leverage, entry_type, status, entry_price, executed_entry_price,
                    remaining_percent, comment, close_reason,
                    result_clean_move_pct, result_personal_move_pct, avg_exit_price,
                    card_message_id, card_chat_id, setup_chat_id,
                    setup_message_id, setup_thread_id, result_points,
                    user_trade_number, last_monitored_at,
                    created_at, opened_at, closed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trade.user_id, trade.user_name, trade.username,
                    trade.exchange, trade.symbol, trade.side.value,
                    trade.leverage, trade.entry_type.value, trade.status.value,
                    trade.entry_price, trade.executed_entry_price,
                    trade.remaining_percent, trade.comment,
                    trade.close_reason.value if trade.close_reason else None,
                    trade.result_clean_move_pct, trade.result_personal_move_pct,
                    trade.avg_exit_price,
                    trade.card_message_id, trade.card_chat_id, trade.setup_chat_id,
                    trade.setup_message_id, trade.setup_thread_id, trade.result_points,
                    trade.user_trade_number,
                    trade.last_monitored_at.isoformat() if trade.last_monitored_at else None,
                    trade.created_at.isoformat() if trade.created_at else _now(),
                    trade.opened_at.isoformat() if trade.opened_at else None,
                    trade.closed_at.isoformat() if trade.closed_at else None,
                ),
            )
            trade_id = cur.lastrowid
            trade.id = trade_id

            if trade.stop_loss:
                await self._insert_sl(db, trade_id, trade.stop_loss)
            for tp in trade.take_profits:
                await self._insert_tp(db, trade_id, tp)
            for ev in trade.events:
                await db.execute(
                    "INSERT INTO trade_events (trade_id, event_type, description, created_at) VALUES (?,?,?,?)",
                    (trade_id, ev.event_type.value, ev.description, ev.created_at.isoformat()),
                )
            await db.commit()
            return await self.get_by_id(trade_id)  # type: ignore

    async def update(self, trade: Trade) -> None:
        async with get_connection() as db:
            await db.execute(
                """
                UPDATE trades SET
                    status=?, entry_price=?, executed_entry_price=?,
                    remaining_percent=?, leverage=?, entry_type=?,
                    comment=?, close_reason=?,
                    result_clean_move_pct=?, result_personal_move_pct=?,
                    avg_exit_price=?, card_message_id=?, card_chat_id=?, setup_chat_id=?,
                    setup_message_id=?, setup_thread_id=?, result_points=?,
                    last_monitored_at=?,
                    opened_at=?, closed_at=?
                WHERE id=?
                """,
                (
                    trade.status.value, trade.entry_price, trade.executed_entry_price,
                    trade.remaining_percent, trade.leverage, trade.entry_type.value,
                    trade.comment,
                    trade.close_reason.value if trade.close_reason else None,
                    trade.result_clean_move_pct, trade.result_personal_move_pct,
                    trade.avg_exit_price, trade.card_message_id, trade.card_chat_id,
                    trade.setup_chat_id,
                    trade.setup_message_id, trade.setup_thread_id, trade.result_points,
                    trade.last_monitored_at.isoformat() if trade.last_monitored_at else None,
                    trade.opened_at.isoformat() if trade.opened_at else None,
                    trade.closed_at.isoformat() if trade.closed_at else None,
                    trade.id,
                ),
            )
            await db.commit()

    async def replace_sl(self, trade_id: int, sl: StopLoss) -> None:
        async with get_connection() as db:
            await db.execute("DELETE FROM stop_losses WHERE trade_id=?", (trade_id,))
            await self._insert_sl(db, trade_id, sl)
            await db.commit()

    async def replace_tps(self, trade_id: int, tps: list[TakeProfitLevel]) -> None:
        async with get_connection() as db:
            await db.execute("DELETE FROM take_profits WHERE trade_id=?", (trade_id,))
            for tp in tps:
                await self._insert_tp(db, trade_id, tp)
            await db.commit()

    async def add_event(
        self,
        trade_id: int,
        event_type: TradeEventType,
        description: str,
        *,
        at: datetime | None = None,
    ) -> None:
        ts = at.isoformat() if at else _now()
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO trade_events (trade_id, event_type, description, created_at) VALUES (?,?,?,?)",
                (trade_id, event_type.value, description, ts),
            )
            await db.commit()

    async def get_by_id(self, trade_id: int) -> Trade | None:
        async with get_connection() as db:
            row = await (await db.execute("SELECT * FROM trades WHERE id=?", (trade_id,))).fetchone()
            if not row:
                return None
            return await self._load(db, row)

    async def list_user_trades(
        self,
        user_id: int,
        *,
        active_only: bool = False,
        closed_only: bool = False,
        limit: int = 30,
    ) -> list[Trade]:
        async with get_connection() as db:
            if active_only:
                query = """
                    SELECT * FROM trades
                    WHERE user_id=? AND status NOT IN ('closed','cancelled')
                    ORDER BY created_at DESC LIMIT ?
                """
                params = (user_id, limit)
            elif closed_only:
                query = """
                    SELECT * FROM trades
                    WHERE user_id=? AND status IN ('closed','cancelled')
                    ORDER BY COALESCE(closed_at, created_at) DESC LIMIT ?
                """
                params = (user_id, limit)
            else:
                query = "SELECT * FROM trades WHERE user_id=? ORDER BY COALESCE(user_trade_number, id) DESC LIMIT ?"
                params = (user_id, limit)
            rows = await (await db.execute(query, params)).fetchall()
            return [await self._load(db, r) for r in rows]

    async def list_user_trades_for_period(self, user_id: int, period: Period) -> list[Trade]:
        """Active trades + closed/cancelled in period, sorted by trade number desc."""
        since = _period_since(period)
        async with get_connection() as db:
            if since is None:
                rows = await (
                    await db.execute(
                        """
                        SELECT * FROM trades WHERE user_id=?
                        ORDER BY COALESCE(user_trade_number, id) DESC
                        """,
                        (user_id,),
                    )
                ).fetchall()
            else:
                since_iso = since.isoformat()
                rows = await (
                    await db.execute(
                        """
                        SELECT * FROM trades WHERE user_id=?
                        AND (
                            status NOT IN ('closed', 'cancelled')
                            OR COALESCE(closed_at, created_at) >= ?
                        )
                        ORDER BY COALESCE(user_trade_number, id) DESC
                        """,
                        (user_id, since_iso),
                    )
                ).fetchall()
            return [await self._load(db, r) for r in rows]

    async def list_open_trades(self) -> list[Trade]:
        async with get_connection() as db:
            rows = await (
                await db.execute(
                    """
                    SELECT * FROM trades
                    WHERE status IN ('open','partially_closed','pending')
                    ORDER BY created_at DESC
                    """
                )
            ).fetchall()
            return [await self._load(db, r) for r in rows]

    async def list_closed_since(self, since: datetime | None) -> list[Trade]:
        async with get_connection() as db:
            if since:
                rows = await (
                    await db.execute(
                        """
                        SELECT * FROM trades
                        WHERE status='closed'
                          AND (closed_at IS NULL OR closed_at>=?)
                        ORDER BY COALESCE(closed_at, created_at) DESC
                        """,
                        (since.isoformat(),),
                    )
                ).fetchall()
            else:
                rows = await (
                    await db.execute(
                        """
                        SELECT * FROM trades
                        WHERE status='closed'
                        ORDER BY COALESCE(closed_at, created_at) DESC
                        """
                    )
                ).fetchall()
            return [await self._load(db, r) for r in rows]

    async def list_user_history_since(
        self, user_id: int, since: datetime | None, limit: int = 30
    ) -> list[Trade]:
        async with get_connection() as db:
            if since:
                rows = await (
                    await db.execute(
                        """
                        SELECT * FROM trades
                        WHERE user_id=? AND status IN ('closed','cancelled')
                          AND (closed_at IS NULL OR closed_at>=?)
                        ORDER BY COALESCE(user_trade_number, id) ASC LIMIT ?
                        """,
                        (user_id, since.isoformat(), limit),
                    )
                ).fetchall()
            else:
                rows = await (
                    await db.execute(
                        """
                        SELECT * FROM trades
                        WHERE user_id=? AND status IN ('closed','cancelled')
                        ORDER BY COALESCE(user_trade_number, id) ASC LIMIT ?
                        """,
                        (user_id, limit),
                    )
                ).fetchall()
            return [await self._load(db, r) for r in rows]

    async def recalc_all_closed_trades(self) -> int:
        async with get_connection() as db:
            rows = await (
                await db.execute("SELECT * FROM trades WHERE status='closed'")
            ).fetchall()
            trades = [await self._load(db, r) for r in rows]

        updated = 0
        for trade in trades:
            changed = False
            clean = trade.result_clean_move_pct or 0.0
            new_lev = normalize_leverage_value(trade.leverage)
            max_lev = await get_max_leverage(trade.exchange, trade.symbol)
            if new_lev > max_lev:
                new_lev = max_lev
            if trade.leverage != new_lev:
                trade.leverage = new_lev
                changed = True
            if trade.closed_at is None:
                trade.closed_at = trade.opened_at or trade.created_at or datetime.now(timezone.utc)
                changed = True
            personal, points = recalc_trade_result(clean, trade.leverage, trade.close_reason)
            if trade.result_personal_move_pct != personal:
                trade.result_personal_move_pct = personal
                changed = True
            if trade.result_points != points:
                trade.result_points = points
                changed = True
            if is_breakeven_close(clean) and trade.close_reason != CloseReason.BREAKEVEN:
                trade.close_reason = CloseReason.BREAKEVEN
                changed = True
            if changed:
                await self.update(trade)
                updated += 1
        return updated

    async def add_partial_exit(self, trade_id: int, price: float, close_percent: float) -> None:
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO partial_exits (trade_id, price, close_percent, closed_at) VALUES (?,?,?,?)",
                (trade_id, price, close_percent, _now()),
            )
            await db.commit()

    async def get_partial_exits(self, trade_id: int) -> list[tuple[float, float]]:
        async with get_connection() as db:
            rows = await (
                await db.execute(
                    "SELECT price, close_percent FROM partial_exits WHERE trade_id=?",
                    (trade_id,),
                )
            ).fetchall()
            return [(r["price"], r["close_percent"] / 100) for r in rows]

    async def get_events(self, trade_id: int) -> list[TradeEvent]:
        async with get_connection() as db:
            rows = await (
                await db.execute(
                    "SELECT * FROM trade_events WHERE trade_id=? ORDER BY created_at",
                    (trade_id,),
                )
            ).fetchall()
            return [
                TradeEvent(
                    id=r["id"], trade_id=r["trade_id"],
                    event_type=TradeEventType(r["event_type"]),
                    description=r["description"],
                    created_at=_parse_dt(r["created_at"]) or datetime.now(timezone.utc),
                )
                for r in rows
            ]

    async def _insert_sl(self, db, trade_id: int, sl: StopLoss) -> None:
        await db.execute(
            """
            INSERT INTO stop_losses (
                trade_id, price, status, executed_price, executed_at,
                trail_mode, trail_value, activation_price, pre_activation_stop,
                extreme_price, trail_active
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                trade_id,
                sl.price,
                sl.status.value,
                sl.executed_price,
                sl.executed_at.isoformat() if sl.executed_at else None,
                sl.trail_mode.value,
                sl.trail_value,
                sl.activation_price,
                sl.pre_activation_stop,
                sl.extreme_price,
                1 if sl.trail_active else 0,
            ),
        )

    async def _insert_tp(self, db, trade_id: int, tp: TakeProfitLevel) -> None:
        await db.execute(
            """
            INSERT INTO take_profits
            (trade_id, order_index, price, close_percent, status, executed_price, executed_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (trade_id, tp.order_index, tp.price, tp.close_percent, tp.status.value,
             tp.executed_price, tp.executed_at.isoformat() if tp.executed_at else None),
        )

    async def _load(self, db, row) -> Trade:
        tid = row["id"]
        tps = await (await db.execute(
            "SELECT * FROM take_profits WHERE trade_id=? ORDER BY order_index", (tid,)
        )).fetchall()
        sl = await (await db.execute(
            "SELECT * FROM stop_losses WHERE trade_id=?", (tid,)
        )).fetchone()

        keys = row.keys()

        def col(name, default=None):
            return row[name] if name in keys else default

        raw_entry_type = row["entry_type"]
        if raw_entry_type == "planned":
            raw_entry_type = "limit"

        return Trade(
            id=tid,
            user_id=row["user_id"],
            user_name=row["user_name"],
            username=row["username"],
            exchange=row["exchange"],
            symbol=row["symbol"],
            side=Side(row["side"]),
            leverage=row["leverage"],
            entry_type=EntryType(raw_entry_type),
            status=TradeStatus(row["status"]),
            entry_price=row["entry_price"],
            executed_entry_price=row["executed_entry_price"],
            remaining_percent=row["remaining_percent"],
            comment=row["comment"],
            close_reason=CloseReason(row["close_reason"]) if row["close_reason"] else None,
            result_clean_move_pct=row["result_clean_move_pct"],
            result_personal_move_pct=row["result_personal_move_pct"],
            avg_exit_price=row["avg_exit_price"],
            card_message_id=row["card_message_id"],
            card_chat_id=row["card_chat_id"],
            setup_chat_id=col("setup_chat_id"),
            setup_message_id=col("setup_message_id"),
            setup_thread_id=col("setup_thread_id"),
            result_points=col("result_points"),
            user_trade_number=col("user_trade_number"),
            last_monitored_at=_parse_dt(col("last_monitored_at")),
            created_at=_parse_dt(row["created_at"]),
            opened_at=_parse_dt(row["opened_at"]),
            closed_at=_parse_dt(row["closed_at"]),
            stop_loss=_load_stop_loss(sl, tid) if sl else None,
            take_profits=[
                TakeProfitLevel(
                    id=tp["id"], trade_id=tid, order_index=tp["order_index"],
                    price=tp["price"], close_percent=tp["close_percent"],
                    status=LevelStatus(tp["status"]),
                    executed_price=tp["executed_price"],
                    executed_at=_parse_dt(tp["executed_at"]),
                )
                for tp in tps
            ],
        )


class StatsRepository:
    async def get_leaderboard(self, period: Period, limit: int = 20) -> list[LeaderboardEntry]:
        since = _period_since(period)

        repo = TradeRepository()
        closed = await repo.list_closed_since(since)

        by_user: dict[int, list] = {}
        names: dict[int, tuple[str, str | None]] = {}
        for t in closed:
            by_user.setdefault(t.user_id, []).append(t)
            names[t.user_id] = (t.user_name, t.username)

        entries: list[LeaderboardEntry] = []
        for uid, trades in by_user.items():
            stats = _calc_stats(uid, names[uid][0], names[uid][1], trades)
            entries.append(LeaderboardEntry(
                rank=0, user_id=uid,
                display_name=stats.display_name, username=stats.username,
                trades_count=stats.trades_count, points=stats.points,
                total_clean_move_pct=stats.total_clean_move_pct,
                total_personal_move_pct=stats.total_personal_move_pct,
                win_rate=stats.win_rate,
            ))

        entries.sort(key=lambda e: e.points, reverse=True)
        ranked = entries[:limit]
        for i, e in enumerate(ranked, 1):
            e.rank = i

        return ranked

    async def get_trader_stats(self, user_id: int, period: Period) -> TraderStats | None:
        since = _period_since(period)

        repo = TradeRepository()
        closed = [t for t in await repo.list_closed_since(since) if t.user_id == user_id]
        if not closed:
            return None
        return _calc_stats(user_id, closed[0].user_name, closed[0].username, closed)


    async def get_trader_closed_trades(self, user_id: int, period: Period) -> list[Trade]:
        since = _period_since(period)
        repo = TradeRepository()
        return await repo.list_user_history_since(user_id, since)


def _period_since(period: Period) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == Period.DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == Period.WEEK:
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == Period.MONTH:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def _calc_stats(user_id, name, username, trades: list[Trade]) -> TraderStats:
    moves = [t.result_clean_move_pct or 0 for t in trades]
    personal = [personal_move_pct(m, t.leverage) for m, t in zip(moves, trades)]
    points_list = [
        calc_trade_points(
            m,
            p,
            force_bu=t.close_reason == CloseReason.BREAKEVEN,
        )
        for m, p, t in zip(moves, personal, trades)
    ]

    win_moves = [m for m in moves if m > BREAKEVEN_THRESHOLD_PCT]
    loss_moves = [m for m in moves if m < 0]
    win_personal = [personal_move_pct(m, t.leverage) for m, t in zip(moves, trades) if m > BREAKEVEN_THRESHOLD_PCT]
    loss_personal = [personal_move_pct(m, t.leverage) for m, t in zip(moves, trades) if m < 0]

    wins = len(win_moves)
    losses = len(loss_moves)
    non_be = sum(1 for m in moves if not is_be_for_stats(m))

    return TraderStats(
        user_id=user_id,
        display_name=name,
        username=username,
        trades_count=len(trades),
        wins=wins,
        losses=losses,
        win_rate=wins / non_be * 100 if non_be else 0,
        points=round(sum(points_list), 2),
        total_clean_move_pct=round(sum(moves), 2),
        total_personal_move_pct=round(sum(personal), 2),
        avg_clean_move_pct=round(sum(moves) / len(trades), 2),
        avg_personal_move_pct=round(sum(personal) / len(trades), 2),
        avg_win_clean_pct=round(sum(win_moves) / len(win_moves), 2) if win_moves else None,
        avg_loss_clean_pct=round(sum(loss_moves) / len(loss_moves), 2) if loss_moves else None,
        avg_win_personal_pct=round(sum(win_personal) / len(win_personal), 2) if win_personal else None,
        avg_loss_personal_pct=round(sum(loss_personal) / len(loss_personal), 2) if loss_personal else None,
        best_trade_pct=max(moves),
        worst_trade_pct=min(moves),
    )
