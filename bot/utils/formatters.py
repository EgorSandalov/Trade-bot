import re

from bot.domain.enums import CloseReason, LevelStatus, TradeEventType, TradeStatus, TrailMode
from bot.domain.models import LeaderboardEntry, StopLoss, Trade, TradeEvent, TraderStats
from bot.keyboards.menus import ENTRY_LABELS, STATUS_LABELS
from bot.domain.exchanges import exchanges_list
from bot.domain.numbers import format_price


def _price(v: float) -> str:
    return format_price(v)


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _pts(v: float) -> str:
    return f"{v:+.2f}"


def _pts_lb(v: float) -> str:
    """Leaderboard points — no + prefix for positive values."""
    return f"{v:.2f}"


def _username_suffix(username: str | None) -> str:
    if not username:
        return ""
    return f" ({username})"


def _trade_no(trade: Trade) -> int:
    return trade.display_number


def format_sl_display(sl: StopLoss | None) -> str:
    if sl is None:
        return "—"
    if sl.trail_mode == TrailMode.FIXED:
        return _price(sl.price)
    unit = f"{sl.trail_value:g}%" if sl.trail_mode == TrailMode.PERCENT else f"{sl.trail_value:g}"
    if sl.pre_activation_stop is not None and not sl.trail_active:
        parts = [f"{_price(sl.pre_activation_stop)} → trail {unit}"]
    else:
        parts = [f"{_price(sl.price)} ↗ trail {unit}"]
    if sl.extreme_price is not None:
        parts.append(f"ext {_price(sl.extreme_price)}")
    if sl.activation_price is not None and not sl.trail_active:
        parts.append(f"act {_price(sl.activation_price)}")
    return " ".join(parts)


def format_setup_confirmed(trade: Trade) -> str:
    side_icon = "🟢" if trade.side.value == "long" else "🔴"
    return (
        f"✅ <b>Trade #{_trade_no(trade)} recorded</b>\n\n"
        f"{side_icon} {trade.symbol.replace('USDT', '')} {trade.side.value.upper()} — {trade.exchange}\n"
        f"Entry: {_price(trade.entry_price)} | {trade.leverage}x\n"
        f"SL: {format_sl_display(trade.stop_loss)}\n"
        f"Status: {STATUS_LABELS.get(trade.status, trade.status.value)}\n\n"
        "/trades — manage"
    )


def _had_trailing_sl(trade: Trade, events: list[TradeEvent] | None) -> bool:
    if trade.stop_loss and trade.stop_loss.trail_mode != TrailMode.FIXED:
        return True
    return any(e.event_type == TradeEventType.SL_TRAILED for e in (events or []))


def _sl_close_label(trade: Trade, events: list[TradeEvent] | None) -> str:
    """Stop-loss exit label — emoji reflects P&L, not just trigger type."""
    clean = trade.result_clean_move_pct or 0.0
    trailing = _had_trailing_sl(trade, events)

    if clean <= -0.01:
        return "🛑 Stop Loss"
    if clean <= 0.2:
        if trailing:
            return "⚖️ Trailing stop · Breakeven"
        return "⚖️ Breakeven stop"
    if trailing:
        return "📈 Trailing stop"
    return "✅ Stop (profit)"


def _close_outcome_label(trade: Trade, events: list[TradeEvent] | None) -> str:
    """Human-readable close path, e.g. TP1 → SL or All TP."""
    tp_nums: list[int] = []
    has_sl = False
    has_manual = False
    for event in events or []:
        if event.event_type == TradeEventType.TP_TRIGGERED:
            match = re.search(r"TP(\d+)", event.description)
            if match:
                tp_nums.append(int(match.group(1)))
        elif event.event_type == TradeEventType.SL_TRIGGERED:
            has_sl = True
        elif event.event_type in (TradeEventType.PARTIAL_CLOSE, TradeEventType.FULL_CLOSE):
            if "market" in event.description.lower():
                has_manual = True

    tp_nums = sorted(set(tp_nums))
    all_tps_hit = bool(
        trade.take_profits
        and all(tp.status == LevelStatus.TRIGGERED for tp in trade.take_profits)
    )
    sl_label = _sl_close_label(trade, events)

    if tp_nums and has_sl:
        tp_part = ", ".join(f"TP{n}" for n in tp_nums)
        label = f"🎯 {tp_part} → {sl_label}"
    elif all_tps_hit and tp_nums:
        label = "🎯 All TP" if len(tp_nums) > 1 else f"🎯 TP{tp_nums[0]}"
    elif tp_nums:
        tp_part = ", ".join(f"TP{n}" for n in tp_nums)
        label = f"🎯 {tp_part}"
    elif has_sl:
        label = sl_label
    elif has_manual or trade.close_reason == CloseReason.MANUAL:
        label = "💰 Manual close"
    else:
        reason_map = {
            CloseReason.TP: "🎯 Take Profit",
            CloseReason.SL: sl_label,
            CloseReason.MANUAL: "💰 Manual close",
            CloseReason.BREAKEVEN: "⚖️ Breakeven",
        }
        label = reason_map.get(trade.close_reason, "Closed")

    if (
        trade.close_reason == CloseReason.BREAKEVEN
        and has_sl
        and "Breakeven" not in label
    ):
        label = f"{label} · Breakeven"
    return label


def format_close_result(trade: Trade, events: list[TradeEvent] | None = None) -> str:
    outcome = _close_outcome_label(trade, events)
    return (
        f"<b>{outcome}</b> — #{_trade_no(trade)} {trade.symbol.replace('USDT', '')} "
        f"{trade.side.value.upper()}\n\n"
        f"Clean move: {_pct(trade.result_clean_move_pct or 0)}\n"
        f"Personal ({trade.leverage}x): {_pct(trade.result_personal_move_pct or 0)}\n"
        f"Points: {_pts(trade.result_points or 0)}"
    )


def format_trade_audit_notes(events: list[TradeEvent] | None) -> str:
    if not events:
        return ""
    lines: list[str] = []
    for e in events:
        if e.event_type == TradeEventType.CANCELLED:
            if e.description.startswith("Trade cancelled:"):
                reason = e.description.split(":", 1)[1].strip()
                if reason:
                    lines.append(f"❌ <b>Cancel reason:</b> {reason}")
        elif e.event_type == TradeEventType.PARAMS_EDITED:
            if "Reason:" in e.description:
                reason = e.description.rsplit("Reason:", 1)[1].strip()
                if reason:
                    lines.append(f"✏️ <b>Edit reason:</b> {reason}")
    if not lines:
        return ""
    return "\n".join(lines)


def format_trade_card(
    trade: Trade,
    current_price: float | None = None,
    *,
    events: list[TradeEvent] | None = None,
) -> str:
    side_icon = "🟢" if trade.side.value == "long" else "🔴"
    lines = [
        f"{side_icon} <b>{trade.symbol.replace('USDT', '')} {trade.side.value.upper()} — {trade.exchange.upper()}</b>",
        "",
        f"Entry: {_price(trade.effective_entry)}",
        f"Type: {ENTRY_LABELS.get(trade.entry_type, trade.entry_type.value)}",
        f"Leverage: {trade.leverage}x",
        f"Status: <b>{STATUS_LABELS.get(trade.status, trade.status.value)}</b>",
        "",
    ]

    if trade.stop_loss:
        sl_mark = "✅" if trade.stop_loss.status.value == "triggered" else ""
        lines.append(f"SL: {format_sl_display(trade.stop_loss)} {sl_mark}")

    if trade.take_profits:
        lines.append("")
        for tp in trade.take_profits:
            mark = "✅" if tp.status.value == "triggered" else "⏳"
            lines.append(f"TP{tp.order_index}: {_price(tp.price)} — {tp.close_percent:.0f}% {mark}")
        lines.append(f"Remaining: {trade.remaining_percent:.0f}%")

    if current_price:
        lines.extend(["", f"Price ({trade.exchange}): {_price(current_price)}"])

    if trade.status == TradeStatus.CLOSED:
        lines.extend([
            "",
            f"Clean: {_pct(trade.result_clean_move_pct or 0)}",
            f"Personal: {_pct(trade.result_personal_move_pct or 0)}",
            f"Points: {_pts(trade.result_points or 0)}",
        ])

    if trade.comment:
        lines.extend(["", f"💬 {trade.comment}"])

    audit = format_trade_audit_notes(events)
    if audit:
        lines.extend(["", audit])

    lines.append(f"\n<i>#{_trade_no(trade)}</i>")
    return "\n".join(lines)


def format_trades_list(
    trades: list[Trade],
    title: str = "My trades",
    empty_text: str = "No trades.",
) -> str:
    if not trades:
        return f"<b>{title}</b>\n\n{empty_text}"
    lines = [f"<b>{title}</b>", "Select a trade:", ""]
    for t in trades:
        status = STATUS_LABELS.get(t.status, t.status.value)
        sym = t.symbol.replace("USDT", "")
        if t.status == TradeStatus.CLOSED and t.result_points is not None:
            lines.append(
                f"#{_trade_no(t)} {sym} {t.side.value.upper()} — "
                f"{status} ({_pts(t.result_points)} pts)"
            )
        elif t.status == TradeStatus.CANCELLED:
            lines.append(f"#{_trade_no(t)} {sym} {t.side.value.upper()} — Cancelled")
        else:
            lines.append(f"#{_trade_no(t)} {sym} {t.side.value.upper()} — {status}")
    return "\n".join(lines)


def format_history(events, trade_number: int | None = None) -> str:
    if not events:
        text = "<b>History</b>\n\nHistory is empty."
    else:
        lines = [
            "<b>History</b>",
            "<i>Times are UTC. Price events use candle/trigger time "
            "(including catch-up after bot downtime).</i>",
            "",
        ]
        for e in events:
            ts = e.created_at.strftime("%d.%m %H:%M UTC")
            lines.append(f"{ts} — {e.description}")
        text = "\n".join(lines)
    if trade_number is not None:
        text += f"\n\n<i>#{trade_number}</i>"
    return text


def _trade_word(n: int) -> str:
    return "trade" if n == 1 else "trades"


def format_leaderboard(
    entries: list[LeaderboardEntry],
    period_label: str,
    *,
    page: int = 0,
    total_pages: int = 1,
) -> str:
    if not entries:
        return f"🏆 <b>Leaderboard · {period_label}</b>\n\nNo closed trades yet."

    title = f"🏆 <b>Leaderboard · {period_label}</b>"
    if total_pages > 1:
        title += f" ({page + 1}/{total_pages})"

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        title,
        "",
        "Tap a trader",
        "",
    ]
    for e in entries:
        medal = medals[e.rank - 1] if e.rank <= 3 and not e.profile_only else f"{e.rank}."
        name = e.display_name + _username_suffix(e.username)
        if e.profile_only:
            lines.append(f"{medal} <i>{name}</i>")
            lines.append("no trades yet")
            lines.append("")
            continue
        lines.append(f"{medal} <b>{name}</b>")
        lines.append(
            f"{_pts_lb(e.points)} pts · {e.trades_count} tr · WR {e.win_rate:.0f}%"
        )
        lines.append(
            f"clean {_pct(e.total_clean_move_pct)} · pers {_pct(e.total_personal_move_pct)}"
        )
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def format_my_trades_header(
    *,
    display_name: str,
    username: str | None,
    period_label: str,
    stats: TraderStats | None,
    trades_count: int,
    page: int = 0,
    total_pages: int = 1,
) -> str:
    label = period_label
    if total_pages > 1:
        label += f" ({page + 1}/{total_pages})"

    if stats:
        text = format_trader_stats(stats, label)
        if trades_count:
            return text + "\n\n<i>Tap a trade below</i>"
        return text

    name = display_name + _username_suffix(username)
    lines = [f"👤 <b>{name}</b>", label, ""]
    if trades_count:
        lines.append("<i>Tap a trade below</i>")
    else:
        lines.append("No trades in this period.")
    return "\n".join(lines)


def format_trader_stats(stats: TraderStats, period_label: str) -> str:
    name = stats.display_name + _username_suffix(stats.username)

    def _avg(v: float | None) -> str:
        return _pct(v) if v is not None else "—"

    return (
        f"👤 <b>{name}</b>\n"
        f"{period_label}\n\n"
        f"{_pts_lb(stats.points)} pts · {stats.trades_count} tr · "
        f"WR {stats.win_rate:.0f}%\n\n"
        f"Clean {_pct(stats.total_clean_move_pct)} · "
        f"avg {_pct(stats.avg_clean_move_pct)}\n"
        f"Win {_avg(stats.avg_win_clean_pct)} · "
        f"Loss {_avg(stats.avg_loss_clean_pct)}\n\n"
        f"Personal {_pct(stats.total_personal_move_pct)} · "
        f"avg {_pct(stats.avg_personal_move_pct)}\n"
        f"Win {_avg(stats.avg_win_personal_pct)} · "
        f"Loss {_avg(stats.avg_loss_personal_pct)}\n\n"
        f"Best {_pct(stats.best_trade_pct or 0)} · "
        f"Worst {_pct(stats.worst_trade_pct or 0)}"
    )


def format_trader_trade_line(trade: Trade) -> str:
    sym = trade.symbol.replace("USDT", "")
    clean = trade.result_clean_move_pct or 0
    pts = trade.result_points or 0
    return f"#{_trade_no(trade)} {sym} {trade.side.value.upper()} — {_pts(pts)} pts ({_pct(clean)})"


def format_trade_detail(trade: Trade, events: list[TradeEvent] | None = None) -> str:
    audit = format_trade_audit_notes(events)

    if trade.status == TradeStatus.CANCELLED:
        lines = [
            f"❌ <b>Cancelled</b> — #{_trade_no(trade)} {trade.symbol.replace('USDT', '')} "
            f"{trade.side.value.upper()}",
            "",
            f"Exchange: {trade.exchange.upper()}",
            f"Entry: {_price(trade.effective_entry)} | {trade.leverage}x",
        ]
        if trade.comment:
            lines.append(f"💬 {trade.comment}")
        if audit:
            lines.append(audit)
        if trade.closed_at:
            lines.append(f"Cancelled: {trade.closed_at.strftime('%d.%m.%Y %H:%M')} UTC")
        return "\n".join(lines)

    lines = [
        format_close_result(trade, events),
        "",
        f"Exchange: {trade.exchange.upper()}",
        f"Entry: {_price(trade.effective_entry)} | {trade.leverage}x",
    ]
    if trade.comment:
        lines.append(f"💬 {trade.comment}")
    if audit:
        lines.append(audit)
    if trade.closed_at:
        lines.append(f"Closed: {trade.closed_at.strftime('%d.%m.%Y %H:%M')} UTC")
    return "\n".join(lines)


def format_help() -> str:
    ex = exchanges_list()
    return (
        "<b>Trade Stats Bot</b>\n\n"
        f"<b>Биржи</b> {ex}\n\n"
        "<b>Команды</b> (General или личка бота)\n"
        "/faq — инструкция RU/EN\n"
        "/trades — ваши сделки\n"
        "/leaderboard — рейтинг\n"
        "/myprofile — banner и sticker (удобно в личке)\n"
        "/chat_id — ID группы\n"
        "/myid — ваш ID\n\n"
        "<b>Сетап</b> (ветка Setups)\n"
        "<pre>OKX\nBTC\nLONG\nType: limit\nLeverage: 10\n"
        "Entry: 95000\nSL: 93000\nTP1: 96000-50%\nTP2: 97000-50%</pre>\n"
        "Trailing: SL: trail 0,5%  или  SL: 75000 + SL: trail 0,5% - 80000\n"
        "Фото с графиком — текст в подписи\n\n"
        "/faq — подробнее"
    )
