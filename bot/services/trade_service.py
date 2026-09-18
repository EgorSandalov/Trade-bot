import logging
from datetime import datetime, timedelta, timezone

from bot.abstractions.repositories import ITradeRepository
from bot.domain.calculations import calc_trade_points, is_breakeven_close, normalize_leverage, personal_move_pct, trade_result_clean_move, weighted_avg_exit
from bot.domain.candles import CandleTrigger, TriggerKind, next_trigger_in_candle, spot_trigger
from bot.domain.enums import (
    CloseReason,
    EntryType,
    LevelStatus,
    Side,
    TradeEventType,
    TradeStatus,
    TrailMode,
)
from bot.domain.models import ParsedStopLoss, ParsedTrade, StopLoss, TakeProfitLevel, Trade, TradeEvent
from bot.domain.parser import validate_price_levels
from bot.domain.trailing import (
    apply_trailing_to_candle,
    apply_trailing_to_spot,
    initial_trailing_state,
    is_trailing,
    parsed_sl_effective_price,
)
from bot.domain.trade_edit import validate_trade_edit
from bot.utils.trade_setup import parse_indexed_take_profits, split_edit_message
from bot.services.leverage_service import validate_leverage
from bot.services.price_service import fetch_candles, fetch_price

log = logging.getLogger(__name__)

_DOWNTIME_REPLAY = timedelta(minutes=3)
_DEEP_REPLAY_COOLDOWN = timedelta(minutes=10)
_DEEP_REPLAY_MIN_AGE = timedelta(hours=1)
_REPLAY_OVERLAP = timedelta(minutes=1)

_LEVEL_CHANGE_EVENTS = frozenset({
    TradeEventType.SL_CHANGED,
    TradeEventType.PARAMS_EDITED,
    TradeEventType.SL_TRAILED,
    TradeEventType.TP_TRIGGERED,
    TradeEventType.ENTRY_CHANGED,
})


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _levels_anchor(trade: Trade, events: list[TradeEvent] | None) -> datetime | None:
    """Earliest time current SL/TP levels must not be replayed before."""
    candidates: list[datetime] = []
    if trade.opened_at:
        candidates.append(trade.opened_at)
    elif trade.created_at:
        candidates.append(trade.created_at)
    for tp in trade.take_profits:
        if tp.executed_at:
            candidates.append(tp.executed_at)
    if events:
        for event in events:
            if event.event_type in _LEVEL_CHANGE_EVENTS:
                candidates.append(event.created_at)
    return max(candidates) if candidates else None


def _tp_replay_anchor(trade: Trade) -> datetime | None:
    """Replay window for catching the next pending TP after downtime."""
    candidates: list[datetime] = []
    if trade.opened_at:
        candidates.append(trade.opened_at)
    elif trade.created_at:
        candidates.append(trade.created_at)
    for tp in trade.take_profits:
        if tp.executed_at:
            candidates.append(tp.executed_at)
    return max(candidates) if candidates else None


def _has_pending_tps(trade: Trade) -> bool:
    return any(tp.status == LevelStatus.PENDING for tp in trade.take_profits)


class TradeService:
    def __init__(self, repo: ITradeRepository) -> None:
        if repo is None:
            raise ValueError("Trade repository must be provided")
        self.repo = repo
        self._monitoring_paused: set[int] = set()
        self._last_deep_replay: dict[int, datetime] = {}

    def pause_monitoring(self, trade_id: int) -> None:
        """Freeze SL/TP checks while user edits or cancels in the diary."""
        self._monitoring_paused.add(trade_id)

    def resume_monitoring(self, trade_id: int) -> None:
        self._monitoring_paused.discard(trade_id)

    def is_monitoring_paused(self, trade_id: int) -> bool:
        return trade_id in self._monitoring_paused

    async def create_from_parsed(
        self,
        user_id: int,
        user_name: str,
        username: str | None,
        parsed: ParsedTrade,
        setup_chat_id: int | None = None,
        setup_message_id: int | None = None,
        setup_thread_id: int | None = None,
        recorded_at: datetime | None = None,
    ) -> Trade:
        err = await validate_leverage(parsed.exchange, parsed.symbol, parsed.leverage)
        if err:
            raise ValueError(err)

        now = _ensure_utc(recorded_at) if recorded_at else datetime.now(timezone.utc)

        if parsed.entry_type == EntryType.MARKET:
            market_price = await fetch_price(parsed.exchange, parsed.symbol)
            if market_price is None:
                raise ValueError(
                    f"Cannot fetch current market price from {parsed.exchange}. "
                    "Try again later or use Type: limit."
                )
            sl_state = initial_trailing_state(parsed.stop_loss, parsed.side, market_price)
            all_level_errors = validate_price_levels(
                market_price,
                parsed.side,
                sl_state.price,
                parsed.take_profits,
                reference_label="market",
            )
            if is_trailing(parsed.stop_loss) and not sl_state.trail_active:
                level_errors = [e for e in all_level_errors if e.startswith("TP")]
            else:
                level_errors = all_level_errors
            if level_errors:
                price_label = f"{market_price:,.0f}" if market_price >= 100 else f"{market_price:.4f}"
                raise ValueError(
                    f"Current {parsed.symbol.replace('USDT', '')} price on "
                    f"{parsed.exchange}: {price_label}\n\n"
                    + "\n".join(f"• {e}" for e in level_errors)
                )
            entry_price = market_price
            status = TradeStatus.OPEN
            executed_entry = market_price
            opened_at = now
        elif parsed.entry_type == EntryType.OPEN:
            entry_price = parsed.entry_price  # type: ignore[assignment]
            status = TradeStatus.OPEN
            executed_entry = entry_price
            opened_at = now
        else:
            entry_price = parsed.entry_price  # type: ignore[assignment]
            status = TradeStatus.PENDING
            executed_entry = None
            opened_at = None

        if parsed.entry_type in (EntryType.LIMIT, EntryType.OPEN) and parsed.entry_price is not None:
            sl_state = initial_trailing_state(
                parsed.stop_loss, parsed.side, parsed.entry_price,
            )
            level_errors = validate_price_levels(
                parsed.entry_price,
                parsed.side,
                sl_state.price,
                parsed.take_profits,
                reference_label="Entry",
            )
            if is_trailing(parsed.stop_loss) and not sl_state.trail_active:
                level_errors = [e for e in level_errors if e.startswith("TP")]
            if level_errors:
                raise ValueError("\n• ".join(level_errors))

        tps = [
            TakeProfitLevel(
                id=None, trade_id=None, order_index=i,
                price=price, close_percent=pct,
            )
            for i, (price, pct) in enumerate(parsed.take_profits, 1)
        ]

        trade = Trade(
            id=None,
            user_id=user_id,
            user_name=user_name,
            username=username,
            exchange=parsed.exchange,
            symbol=parsed.symbol,
            side=parsed.side,
            leverage=parsed.leverage,
            entry_type=parsed.entry_type,
            status=status,
            entry_price=entry_price,
            executed_entry_price=executed_entry,
            stop_loss=initial_trailing_state(
                parsed.stop_loss,
                parsed.side,
                entry_price,
            ),
            take_profits=tps,
            comment=parsed.comment,
            setup_chat_id=setup_chat_id,
            setup_message_id=setup_message_id,
            setup_thread_id=setup_thread_id,
            created_at=now,
            opened_at=opened_at,
            events=[
                TradeEvent(None, 0, TradeEventType.CREATED, "Trade created", now),
            ],
        )
        if status == TradeStatus.OPEN:
            label = "Market" if parsed.entry_type == EntryType.MARKET else "Open"
            trade.events.append(
                TradeEvent(
                    None, 0, TradeEventType.ENTRY_FILLED,
                    f"{label} entry: ${entry_price:,.2f}", now,
                )
            )
        return await self.repo.create(trade)

    async def set_card_message(self, trade_id: int, chat_id: int, message_id: int) -> None:
        trade = await self.repo.get_by_id(trade_id)
        if trade:
            trade.card_chat_id = chat_id
            trade.card_message_id = message_id
            await self.repo.update(trade)

    async def fill_entry(
        self,
        trade: Trade,
        price: float | None = None,
        *,
        filled_at: datetime | None = None,
    ) -> Trade:
        p = price or trade.entry_price
        when = _ensure_utc(filled_at) if filled_at else datetime.now(timezone.utc)
        trade.executed_entry_price = p
        trade.status = TradeStatus.OPEN
        trade.opened_at = when
        await self.repo.update(trade)
        label = "Limit" if trade.entry_type == EntryType.LIMIT else "Entry"
        await self.repo.add_event(
            trade.id,
            TradeEventType.ENTRY_FILLED,
            f"{label} entry: ${p:,.2f}",
            at=when,
        )
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def update_entry(self, trade: Trade, new_price: float) -> Trade:
        sl_price = trade.stop_loss.price if trade.stop_loss else 0.0
        tp_prices = [(tp.price, tp.close_percent) for tp in trade.take_profits]
        errors = validate_price_levels(new_price, trade.side, sl_price, tp_prices)
        if errors:
            raise ValueError(
                "After this Entry change, levels are invalid:\n• "
                + "\n• ".join(errors)
                + "\n\nUpdate SL/TP first or choose another Entry."
            )

        old = trade.entry_price
        trade.entry_price = new_price
        if trade.status == TradeStatus.OPEN:
            trade.executed_entry_price = new_price
        await self.repo.update(trade)
        await self.repo.add_event(
            trade.id, TradeEventType.ENTRY_CHANGED, f"Entry: ${old:,.2f} → ${new_price:,.2f}"
        )
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def update_sl(self, trade: Trade, new_price: float) -> Trade:
        entry = trade.entry_price
        tp_prices = [(tp.price, tp.close_percent) for tp in trade.take_profits]
        errors = validate_price_levels(entry, trade.side, new_price, tp_prices)
        if errors:
            raise ValueError("\n• ".join(errors))
        if not trade.stop_loss:
            trade.stop_loss = StopLoss(id=None, trade_id=trade.id, price=new_price)
        else:
            old = trade.stop_loss.price
            trade.stop_loss.price = new_price
            await self.repo.add_event(
                trade.id, TradeEventType.SL_CHANGED, f"SL: ${old:,.2f} → ${new_price:,.2f}"
            )
        await self.repo.replace_sl(trade.id, trade.stop_loss)
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def update_leverage(self, trade: Trade, leverage: int) -> Trade:
        err = await validate_leverage(trade.exchange, trade.symbol, leverage)
        if err:
            raise ValueError(err)
        old = trade.leverage
        trade.leverage = leverage
        await self.repo.update(trade)
        await self.repo.add_event(
            trade.id, TradeEventType.LEVERAGE_CHANGED, f"Leverage: {old}x → {leverage}x"
        )
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def trigger_tp(
        self,
        trade: Trade,
        tp_index: int,
        exit_price: float | None = None,
        *,
        executed_at: datetime | None = None,
    ) -> Trade:
        tp = next((t for t in trade.take_profits if t.order_index == tp_index), None)
        if not tp or tp.status != LevelStatus.PENDING:
            raise ValueError("TP unavailable")

        price = exit_price or tp.price
        when = _ensure_utc(executed_at) if executed_at else datetime.now(timezone.utc)
        tp.status = LevelStatus.TRIGGERED
        tp.executed_price = price
        tp.executed_at = when
        trade.remaining_percent -= tp.close_percent

        if trade.remaining_percent <= 0.01:
            await self._finalize(trade, CloseReason.TP, closed_at=when)
        else:
            trade.status = TradeStatus.PARTIALLY_CLOSED
            await self.repo.update(trade)
            await self.repo.replace_tps(trade.id, trade.take_profits)
            await self.repo.add_event(
                trade.id,
                TradeEventType.TP_TRIGGERED,
                f"TP{tp_index}: ${price:,.2f}, close {tp.close_percent:.0f}%, remaining {trade.remaining_percent:.0f}%",
                at=when,
            )
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def trigger_sl(
        self,
        trade: Trade,
        exit_price: float | None = None,
        *,
        executed_at: datetime | None = None,
    ) -> Trade:
        if not trade.stop_loss:
            raise ValueError("SL not set")
        price = exit_price or trade.stop_loss.price
        when = _ensure_utc(executed_at) if executed_at else datetime.now(timezone.utc)
        trade.stop_loss.status = LevelStatus.TRIGGERED
        trade.stop_loss.executed_price = price
        trade.stop_loss.executed_at = when
        remaining_at_sl = trade.remaining_percent
        trade.remaining_percent = 0
        await self.repo.replace_sl(trade.id, trade.stop_loss)
        await self.repo.add_event(
            trade.id,
            TradeEventType.SL_TRIGGERED,
            f"SL: ${price:,.2f}, close {remaining_at_sl:.0f}% remaining",
            at=when,
        )
        await self._finalize(
            trade,
            CloseReason.SL,
            force_exit_price=price,
            sl_remaining_percent=remaining_at_sl,
            closed_at=when,
        )
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def partial_close(
        self, trade: Trade, close_percent: float, force_breakeven: bool = False
    ) -> Trade:
        if trade.status not in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
            raise ValueError("Trade is not open")

        close_percent = min(close_percent, trade.remaining_percent)
        market = await fetch_price(trade.exchange, trade.symbol)
        if market is None:
            raise ValueError("Cannot fetch price from exchange. Try again later.")

        await self.repo.add_event(
            trade.id, TradeEventType.PARTIAL_CLOSE,
            f"Closed {close_percent:.0f}% at market ${market:,.2f}",
        )

        trade.remaining_percent -= close_percent
        await self.repo.add_partial_exit(trade.id, market, close_percent)

        if trade.remaining_percent <= 0.01:
            reason = CloseReason.BREAKEVEN if force_breakeven else CloseReason.MANUAL
            await self._finalize(trade, reason, force_breakeven=force_breakeven)
        else:
            trade.status = TradeStatus.PARTIALLY_CLOSED
            await self.repo.update(trade)
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def cancel_trade(self, trade: Trade, reason: str | None = None) -> Trade:
        trade.status = TradeStatus.CANCELLED
        trade.closed_at = datetime.now(timezone.utc)
        await self.repo.update(trade)
        if reason:
            desc = f"Trade cancelled: {reason}"
        else:
            desc = "Trade cancelled"
        await self.repo.add_event(trade.id, TradeEventType.CANCELLED, desc)
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def apply_trade_edit(
        self,
        trade: Trade,
        raw_text: str,
        current_price: float | None = None,
    ) -> Trade:
        parsed, reason, errors = validate_trade_edit(trade, raw_text, current_price)
        if errors or parsed is None:
            raise ValueError("\n• ".join(errors))

        indexed_tps = parse_indexed_take_profits(split_edit_message(raw_text)[0])
        changes: list[str] = []

        if parsed.leverage != trade.leverage:
            err = await validate_leverage(trade.exchange, trade.symbol, parsed.leverage)
            if err:
                raise ValueError(err)
            changes.append(f"Leverage: {trade.leverage}x → {parsed.leverage}x")
            trade.leverage = parsed.leverage

        if parsed.entry_type != EntryType.MARKET and parsed.entry_price is not None:
            if parsed.entry_price != trade.entry_price:
                changes.append(
                    f"Entry: ${trade.entry_price:,.2f} → ${parsed.entry_price:,.2f}"
                )
                trade.entry_price = parsed.entry_price
                if trade.status in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
                    trade.executed_entry_price = parsed.entry_price

        sl_ref = current_price if current_price is not None else trade.effective_entry
        new_sl = initial_trailing_state(parsed.stop_loss, trade.side, sl_ref)
        old_sl = trade.stop_loss
        sl_changed = (
            old_sl is None
            or old_sl.trail_mode != new_sl.trail_mode
            or old_sl.trail_value != new_sl.trail_value
            or old_sl.activation_price != new_sl.activation_price
            or old_sl.pre_activation_stop != new_sl.pre_activation_stop
            or (old_sl.trail_mode == TrailMode.FIXED and old_sl.price != new_sl.price)
        )
        if sl_changed:
            if old_sl and old_sl.trail_mode == TrailMode.FIXED and new_sl.trail_mode == TrailMode.FIXED:
                changes.append(f"SL: ${old_sl.price:,.2f} → ${new_sl.price:,.2f}")
            else:
                from bot.domain.trailing import format_sl_line

                changes.append(f"SL → {format_sl_line(parsed.stop_loss)}")
            if old_sl:
                new_sl.id = old_sl.id
                new_sl.trade_id = old_sl.trade_id
                new_sl.status = old_sl.status
            trade.stop_loss = new_sl
            await self.repo.replace_sl(trade.id, trade.stop_loss)

        if parsed.comment != trade.comment:
            if parsed.comment:
                changes.append(f"Comment updated")
            trade.comment = parsed.comment

        triggered = [tp for tp in trade.take_profits if tp.status == LevelStatus.TRIGGERED]
        new_pending = [
            TakeProfitLevel(
                id=None,
                trade_id=trade.id,
                order_index=idx,
                price=price,
                close_percent=pct,
            )
            for idx, price, pct in indexed_tps
        ]
        if new_pending:
            tp_desc = ", ".join(
                f"TP{tp.order_index} ${tp.price:,.0f} ({tp.close_percent:.0f}%)"
                for tp in new_pending
            )
            changes.append(f"Pending TPs: {tp_desc}")
        trade.take_profits = sorted(triggered + new_pending, key=lambda t: t.order_index)
        await self.repo.replace_tps(trade.id, trade.take_profits)

        if not changes:
            if reason:
                await self.repo.add_event(
                    trade.id,
                    TradeEventType.PARAMS_EDITED,
                    f"No parameter changes. Reason: {reason}",
                )
                await self.repo.update(trade)
            return await self.repo.get_by_id(trade.id)  # type: ignore

        summary = "; ".join(changes)
        if reason:
            desc = f"{summary}. Reason: {reason}"
        else:
            desc = summary
        await self.repo.add_event(trade.id, TradeEventType.PARAMS_EDITED, desc)
        await self.repo.update(trade)
        return await self.repo.get_by_id(trade.id)  # type: ignore

    async def market_close(self, trade: Trade) -> Trade:
        """Close the remaining position at the current market price."""
        if trade.status not in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
            raise ValueError("Trade is not open")
        return await self.partial_close(trade, trade.remaining_percent)

    async def check_price_triggers(self, trade: Trade, *, full_replay: bool = False) -> Trade:
        if trade.id is not None and self.is_monitoring_paused(trade.id):
            return trade
        now = datetime.now(timezone.utc)
        events = await self.repo.get_events(trade.id) if trade.id else []
        since = self._replay_since(trade, now, full_replay=full_replay, events=events)
        if full_replay and trade.id is not None:
            self._last_deep_replay[trade.id] = now

        candles = await fetch_candles(trade.exchange, trade.symbol, since, now)
        expected_minutes = max(0.0, (now - since).total_seconds() / 60.0)
        if candles:
            trade = await self._apply_candle_history(trade, candles)
        elif expected_minutes > 5:
            log.warning(
                "No candles for trade #%s (%s %s) over %.0f min — spot check only",
                trade.display_number or trade.id,
                trade.exchange,
                trade.symbol,
                expected_minutes,
            )

        if (
            trade.status in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED)
            and _has_pending_tps(trade)
        ):
            tp_anchor = _tp_replay_anchor(trade)
            if tp_anchor is not None:
                tp_since = max(self._trade_start(trade), tp_anchor - _REPLAY_OVERLAP)
                if tp_since < since - timedelta(seconds=30):
                    extra = await fetch_candles(
                        trade.exchange, trade.symbol, tp_since, since,
                    )
                    if extra:
                        log.info(
                            "Trade #%s TP catch-up: %d extra candles from %s",
                            trade.display_number or trade.id,
                            len(extra),
                            tp_since.strftime("%H:%M UTC"),
                        )
                        trade = await self._apply_tp_candle_history(trade, extra)

        if trade.status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
            price = await fetch_price(trade.exchange, trade.symbol)
            if price is not None:
                trade = await self._apply_spot_trigger(trade, price)

        trade.last_monitored_at = now
        await self.repo.update(trade)
        return await self.repo.get_by_id(trade.id)  # type: ignore

    def _trade_start(self, trade: Trade) -> datetime:
        if trade.status == TradeStatus.PENDING and trade.created_at:
            return trade.created_at
        if trade.opened_at:
            return trade.opened_at
        if trade.created_at:
            return trade.created_at
        return datetime.now(timezone.utc) - timedelta(hours=24)

    def _needs_deep_replay(self, trade: Trade, now: datetime) -> bool:
        """Full history replay when incremental checks likely missed triggers."""
        if trade.id is not None and self.is_monitoring_paused(trade.id):
            return False
        if trade.status not in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
            return False
        if trade.remaining_percent < 99.9:
            if trade.last_monitored_at and now - trade.last_monitored_at > _DOWNTIME_REPLAY:
                return True
            return False
        start = self._trade_start(trade)
        if now - start < _DEEP_REPLAY_MIN_AGE:
            return False
        if trade.id is not None:
            last = self._last_deep_replay.get(trade.id)
            if last and now - last < _DEEP_REPLAY_COOLDOWN:
                return False
        return True

    def _replay_since(
        self,
        trade: Trade,
        now: datetime,
        *,
        full_replay: bool,
        events: list[TradeEvent] | None,
    ) -> datetime:
        start = self._trade_start(trade)
        anchor = _levels_anchor(trade, events)
        min_since = (anchor - _REPLAY_OVERLAP) if anchor else start

        since = max(start, min_since)
        if _has_pending_tps(trade) and trade.remaining_percent < 99.9:
            tp_anchor = _tp_replay_anchor(trade)
            if tp_anchor is not None:
                tp_since = max(start, tp_anchor - _REPLAY_OVERLAP)
                since = min(since, tp_since)
        if full_replay:
            if (
                trade.remaining_percent < 99.9
                and trade.last_monitored_at
                and now - trade.last_monitored_at > _DOWNTIME_REPLAY
            ):
                monitor_since = max(start, trade.last_monitored_at - _REPLAY_OVERLAP)
                since = min(since, monitor_since)
            return since

        if not trade.last_monitored_at:
            return max(start, min_since)

        gap = now - trade.last_monitored_at
        if gap > _DOWNTIME_REPLAY:
            since = trade.last_monitored_at - _REPLAY_OVERLAP
            return max(since, min_since)

        if self._needs_deep_replay(trade, now):
            if trade.id is not None:
                self._last_deep_replay[trade.id] = now
            return max(start, min_since)

        since = trade.last_monitored_at - _REPLAY_OVERLAP
        return max(since, min_since)

    def _monitor_since(self, trade: Trade, now: datetime) -> datetime:
        """Backward-compatible wrapper for tests."""
        return self._replay_since(trade, now, full_replay=False, events=None)

    async def _persist_trailing_sl(
        self,
        trade: Trade,
        prev_price: float,
        *,
        at: datetime | None = None,
    ) -> None:
        if not trade.stop_loss or not trade.id:
            return
        sl = trade.stop_loss
        await self.repo.replace_sl(trade.id, sl)
        if sl.trail_active and sl.trail_mode != TrailMode.FIXED:
            await self.repo.add_event(
                trade.id,
                TradeEventType.SL_TRAILED,
                f"Trailing SL: ${prev_price:,.2f} → ${sl.price:,.2f} "
                f"(ext ${sl.extreme_price:,.2f})" if sl.extreme_price else
                f"Trailing SL: ${prev_price:,.2f} → ${sl.price:,.2f}",
                at=at,
            )

    async def _apply_trailing_candle(
        self,
        trade: Trade,
        *,
        high: float,
        low: float,
        at: datetime | None = None,
    ) -> Trade:
        if not trade.stop_loss or trade.stop_loss.trail_mode == TrailMode.FIXED:
            return trade
        prev = trade.stop_loss.price
        was_active = trade.stop_loss.trail_active
        _, changed = apply_trailing_to_candle(trade, high=high, low=low)
        if changed and trade.id:
            if not was_active and trade.stop_loss.trail_active:
                await self.repo.add_event(
                    trade.id,
                    TradeEventType.SL_CHANGED,
                    f"Trailing activated @ ${trade.stop_loss.extreme_price:,.2f}",
                    at=at,
                )
            await self._persist_trailing_sl(trade, prev, at=at)
            trade = await self.repo.get_by_id(trade.id)  # type: ignore[assignment]
        return trade

    async def _apply_candle_history(self, trade: Trade, candles: list) -> Trade:
        for candle in candles:
            if trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
                break
            trade = await self._process_candle_triggers(trade, candle)
            if trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
                continue
            trade = await self._apply_trailing_candle(
                trade, high=candle.high, low=candle.low, at=candle.ts,
            )
            if (
                trade.status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED)
                and is_trailing(trade.stop_loss)
            ):
                trade = await self._process_candle_triggers(trade, candle, tp_only=True)
        return trade

    async def _apply_tp_candle_history(self, trade: Trade, candles: list) -> Trade:
        """Replay pending TPs only — safe when SL anchor is newer than last TP."""
        for candle in candles:
            if trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
                break
            if not _has_pending_tps(trade):
                break
            trade = await self._process_candle_triggers(trade, candle, tp_only=True)
        return trade

    async def _process_candle_triggers(
        self,
        trade: Trade,
        candle,
        *,
        tp_only: bool = False,
    ) -> Trade:
        while trade.status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
            trigger = next_trigger_in_candle(trade, candle, tp_only=tp_only)
            if trigger is None:
                break
            trade = await self._execute_trigger(trade, trigger)
        return trade

    async def _apply_spot_trigger(self, trade: Trade, price: float) -> Trade:
        while trade.status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
            trigger = spot_trigger(trade, price)
            if trigger is None:
                break
            trade = await self._execute_trigger(trade, trigger)
        if trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
            return trade
        trade = await self._apply_trailing_candle(trade, high=price, low=price)
        while trade.status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
            trigger = spot_trigger(trade, price)
            if trigger is None:
                break
            if trigger.kind == TriggerKind.STOP_LOSS and is_trailing(trade.stop_loss):
                break
            trade = await self._execute_trigger(trade, trigger)
        return trade

    async def _execute_trigger(self, trade: Trade, trigger: CandleTrigger) -> Trade:
        at = trigger.at
        if trigger.kind == TriggerKind.FILL_ENTRY:
            return await self.fill_entry(trade, trigger.price, filled_at=at)
        if trigger.kind == TriggerKind.STOP_LOSS:
            return await self.trigger_sl(trade, trigger.price, executed_at=at)
        if trigger.kind == TriggerKind.TAKE_PROFIT and trigger.tp_index is not None:
            return await self.trigger_tp(
                trade, trigger.tp_index, trigger.price, executed_at=at,
            )
        return trade

    async def _finalize(
        self,
        trade: Trade,
        reason: CloseReason,
        force_exit_price: float | None = None,
        force_breakeven: bool = False,
        sl_remaining_percent: float | None = None,
        *,
        closed_at: datetime | None = None,
    ) -> None:
        exits: list[tuple[float, float]] = []
        for tp in trade.take_profits:
            if tp.status == LevelStatus.TRIGGERED and tp.executed_price:
                exits.append((tp.executed_price, tp.close_percent / 100))

        for price, fraction in await self.repo.get_partial_exits(trade.id):
            exits.append((price, fraction))

        if reason == CloseReason.SL and force_exit_price:
            remaining_pct = (
                sl_remaining_percent
                if sl_remaining_percent is not None
                else trade.remaining_percent
            )
            remaining = remaining_pct / 100
            if remaining > 0:
                exits.append((force_exit_price, remaining))

        if not exits and force_exit_price:
            exits.append((force_exit_price, 1.0))

        entry = trade.effective_entry
        trade.result_clean_move_pct = trade_result_clean_move(entry, trade.side, exits)
        trade.leverage = normalize_leverage(trade.leverage)
        trade.result_personal_move_pct = personal_move_pct(
            trade.result_clean_move_pct, trade.leverage
        )

        bu = force_breakeven or reason == CloseReason.BREAKEVEN
        if not bu:
            bu = is_breakeven_close(trade.result_clean_move_pct)
        if bu:
            trade.close_reason = CloseReason.BREAKEVEN
        else:
            trade.close_reason = reason

        trade.result_points = calc_trade_points(
            trade.result_clean_move_pct,
            trade.result_personal_move_pct,
            force_bu=bu,
        )
        trade.avg_exit_price = weighted_avg_exit(exits)
        trade.status = TradeStatus.CLOSED
        trade.remaining_percent = 0
        when = _ensure_utc(closed_at) if closed_at else datetime.now(timezone.utc)
        trade.closed_at = when

        await self.repo.update(trade)
        await self.repo.replace_tps(trade.id, trade.take_profits)
        await self.repo.add_event(
            trade.id, TradeEventType.FULL_CLOSE,
            f"Closed. Clean: {trade.result_clean_move_pct:+.2f}%, "
            f"Personal: {trade.result_personal_move_pct:+.2f}%, "
            f"Points: {trade.result_points:+.2f}",
            at=when,
        )
