from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.domain.enums import EntryType, Period, TradeStatus

LEADERBOARD_PAGE_SIZE = 6
TRADER_TRADES_PAGE_SIZE = 6
MY_TRADES_PAGE_SIZE = 4


def _trade_ctx(period: Period | str, page: int = 0) -> str:
    value = period.value if isinstance(period, Period) else period
    return f"{value}:{page}"


def parse_trade_ctx(ctx: str | None) -> tuple[str | None, int]:
    if not ctx:
        return None, 0
    if ctx in ("active", "closed"):
        return Period.ALL.value, 0
    parts = ctx.split(":")
    if len(parts) >= 2 and parts[-1].isdigit():
        return parts[0], int(parts[-1])
    return ctx, 0


def neighbor_trade_ids(trades, trade_id: int) -> tuple[int | None, int | None]:
    """List is newest-first; prev = older (#lower), next = newer (#higher)."""
    ordered = [t.id for t in trades if t.id is not None]
    try:
        idx = ordered.index(trade_id)
    except ValueError:
        return None, None
    prev_id = ordered[idx + 1] if idx + 1 < len(ordered) else None
    next_id = ordered[idx - 1] if idx > 0 else None
    return prev_id, next_id


def _trade_neighbor_row(
    trade_id: int,
    trades,
    *,
    make_callback,
) -> list[InlineKeyboardButton] | None:
    prev_id, next_id = neighbor_trade_ids(trades, trade_id)
    if prev_id is None and next_id is None:
        return None
    row: list[InlineKeyboardButton] = []
    if prev_id is not None:
        row.append(InlineKeyboardButton(text="◀ Prev", callback_data=make_callback(prev_id)))
    if next_id is not None:
        row.append(InlineKeyboardButton(text="Next ▶", callback_data=make_callback(next_id)))
    return row


def profile_menu_kb(
    *,
    has_sticker: bool = False,
    has_loss_sticker: bool = False,
    hide: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if hide != "banner":
        rows.append([InlineKeyboardButton(text="🖼 Banner", callback_data="prof:banner")])
    sticker_row: list[InlineKeyboardButton] = []
    if hide != "reaction":
        sticker_row.append(InlineKeyboardButton(text="🔥 Sticker", callback_data="prof:reaction"))
    if hide != "loss_reaction":
        sticker_row.append(InlineKeyboardButton(text="💀 Sticker", callback_data="prof:loss_reaction"))
    if sticker_row:
        rows.append(sticker_row)
    if hide is None:
        preview_row: list[InlineKeyboardButton] = []
        if has_sticker:
            preview_row.append(
                InlineKeyboardButton(text="👁 +100%", callback_data="prof:preview_sticker"),
            )
        if has_loss_sticker:
            preview_row.append(
                InlineKeyboardButton(text="👁 -100%", callback_data="prof:preview_loss_sticker"),
            )
        if preview_row:
            rows.append(preview_row)
    if hide is not None:
        rows.append([InlineKeyboardButton(text="◀ Back", callback_data="prof:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_saved_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Back to profile", callback_data="prof:menu")],
    ])


def profile_preview_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Back", callback_data="prof:menu")],
    ])


def trade_card_kb(
    trade_id: int,
    status: TradeStatus,
    period: str | None = None,
    page: int = 0,
    trades: list | None = None,
) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page) if period else ""
    suffix = f":{ctx}" if ctx else ""
    rows = []
    if trades:
        nav = _trade_neighbor_row(
            trade_id,
            trades,
            make_callback=lambda tid: f"t:{tid}:open:{ctx}",
        )
        if nav:
            rows.append(nav)
    if status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
        rows.append([
            InlineKeyboardButton(text="⚙️ Edit", callback_data=f"t:{trade_id}:edit:{ctx}"),
            InlineKeyboardButton(text="🔄 Price", callback_data=f"t:{trade_id}:refresh:{ctx}"),
        ])
        rows.append([
            InlineKeyboardButton(text="📤 Market close", callback_data=f"t:{trade_id}:ask_market:{ctx}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"t:{trade_id}:ask_cancel:{ctx}"),
        ])
    elif status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
        rows.append([
            InlineKeyboardButton(text="📜 History", callback_data=f"t:{trade_id}:history:{ctx}"),
        ])
    if period:
        rows.append([
            InlineKeyboardButton(text="◀ My trades", callback_data=f"mt:{period}:{page}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_prompt_kb(trade_id: int, period: str | None = None, page: int = 0) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page) if period else ""
    suffix = f":{ctx}" if ctx else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Back", callback_data=f"t:{trade_id}:refresh{suffix}")],
    ])


def cancel_prompt_kb(trade_id: int, period: str | None = None, page: int = 0) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page) if period else ""
    suffix = f":{ctx}" if ctx else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Skip", callback_data=f"t:{trade_id}:cancel_skip{suffix}"),
            InlineKeyboardButton(text="◀ Back", callback_data=f"t:{trade_id}:refresh{suffix}"),
        ],
    ])


def market_close_prompt_kb(trade_id: int, period: str | None = None, page: int = 0) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page) if period else ""
    suffix = f":{ctx}" if ctx else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Close now", callback_data=f"t:{trade_id}:market_confirm{suffix}"),
            InlineKeyboardButton(text="◀ Back", callback_data=f"t:{trade_id}:refresh{suffix}"),
        ],
    ])


def history_back_kb(trade_id: int, period: str | None = None, page: int = 0) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page) if period else ""
    suffix = f":{ctx}" if ctx else ""
    rows = [[InlineKeyboardButton(
        text="◀ Back to trade",
        callback_data=f"t:{trade_id}:refresh{suffix}",
    )]]
    if period:
        rows.append([InlineKeyboardButton(text="◀ My trades", callback_data=f"mt:{period}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _leaderboard_period_rows(current=None) -> list[list[InlineKeyboardButton]]:
    from bot.domain.enums import Period

    options = [
        (Period.DAY, "📅 Today"),
        (Period.WEEK, "📆 Week"),
        (Period.MONTH, "🗓 Month"),
        (Period.ALL, "🏆 All time"),
    ]
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"lb:{period.value}")
        for period, label in options
        if period != current
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i + 2])
    return rows


def leaderboard_period_kb(*, current=None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=_leaderboard_period_rows(current))


def leaderboard_traders_kb(entries, period, page: int = 0) -> InlineKeyboardMarkup:
    from bot.domain.enums import Period

    page_entries, page, total_pages = paginate_leaderboard(entries, period, page)
    rows = []
    for e in page_entries:
        if e.profile_only:
            label = f"{e.rank}. {e.display_name} (no trades)"
            rows.append([InlineKeyboardButton(
                text=label,
                callback_data=f"lp:{e.user_id}:{period.value}",
            )])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{e.rank}. {e.display_name} ({_pts_lb(e.points)} pts)",
                callback_data=f"tr:{e.user_id}:{period.value}",
            )])
    rows.extend(_leaderboard_page_nav(period, page, total_pages))
    rows.extend(_leaderboard_period_rows(period))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paginate_leaderboard(entries, period, page: int = 0):
    if len(entries) > LEADERBOARD_PAGE_SIZE:
        total_pages = max(1, (len(entries) + LEADERBOARD_PAGE_SIZE - 1) // LEADERBOARD_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * LEADERBOARD_PAGE_SIZE
        return entries[start:start + LEADERBOARD_PAGE_SIZE], page, total_pages
    return entries, 0, 1


def paginate_trader_trades(trades, page: int = 0):
    if len(trades) > TRADER_TRADES_PAGE_SIZE:
        total_pages = max(1, (len(trades) + TRADER_TRADES_PAGE_SIZE - 1) // TRADER_TRADES_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * TRADER_TRADES_PAGE_SIZE
        return trades[start:start + TRADER_TRADES_PAGE_SIZE], page, total_pages
    return trades, 0, 1


def _trader_trades_page_nav(user_id: int, period, page: int, total_pages: int) -> list[list[InlineKeyboardButton]]:
    if total_pages <= 1:
        return []
    period_value = period.value if isinstance(period, Period) else period
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"tr:{user_id}:{period_value}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="tr:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"tr:{user_id}:{period_value}:{page + 1}"))
    return [nav]


def _leaderboard_page_nav(period, page: int, total_pages: int) -> list[list[InlineKeyboardButton]]:
    if total_pages <= 1:
        return []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"lb:{period.value}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="lb:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"lb:{period.value}:{page + 1}"))
    return [nav]


def paginate_my_trades(trades, page: int = 0):
    if len(trades) > MY_TRADES_PAGE_SIZE:
        total_pages = max(1, (len(trades) + MY_TRADES_PAGE_SIZE - 1) // MY_TRADES_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * MY_TRADES_PAGE_SIZE
        return trades[start:start + MY_TRADES_PAGE_SIZE], page, total_pages
    return trades, 0, 1


def _my_trades_period_rows(current: Period | None = None) -> list[list[InlineKeyboardButton]]:
    options = [
        (Period.DAY, "📅 Today"),
        (Period.WEEK, "📆 Week"),
        (Period.MONTH, "🗓 Month"),
        (Period.ALL, "🏆 All time"),
    ]
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"mt:{period.value}:0")
        for period, label in options
        if period != current
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i + 2])
    return rows


def _my_trades_page_nav(period: Period, page: int, total_pages: int) -> list[list[InlineKeyboardButton]]:
    if total_pages <= 1:
        return []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"mt:{period.value}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="mt:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"mt:{period.value}:{page + 1}"))
    return [nav]


def my_trades_kb(trades, period: Period, page: int = 0) -> InlineKeyboardMarkup:
    _, page, total_pages = paginate_my_trades(trades, page)
    page_trades, _, _ = paginate_my_trades(trades, page)
    rows = [
        [InlineKeyboardButton(
            text=my_trade_button_label(t),
            callback_data=f"t:{t.id}:open:{_trade_ctx(period, page)}",
        )]
        for t in page_trades
    ]
    rows.extend(_my_trades_page_nav(period, page, total_pages))
    rows.extend(_my_trades_period_rows(period))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_trade_button_label(trade) -> str:
    sym = trade.symbol.replace("USDT", "")
    side = trade.side.value.upper()
    num = trade.user_trade_number or trade.id
    if trade.status == TradeStatus.CLOSED and trade.result_points is not None:
        return f"#{num} {sym} {side} ({_pts_lb(trade.result_points)} pts)"
    if trade.status == TradeStatus.CANCELLED:
        return f"#{num} {sym} {side} — Cancelled"
    status = STATUS_LABELS.get(trade.status, trade.status.value)
    return f"#{num} {sym} {side} — {status}"


def my_trade_active_kb(
    trade_id: int,
    period: str,
    page: int,
    setup_url: str | None,
    trades: list | None = None,
) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page)
    rows: list[list[InlineKeyboardButton]] = []
    if setup_url:
        rows.append([InlineKeyboardButton(text="📎 Open setup", url=setup_url)])
    if trades:
        nav = _trade_neighbor_row(
            trade_id,
            trades,
            make_callback=lambda tid: f"t:{tid}:open:{ctx}",
        )
        if nav:
            rows.append(nav)
    rows.append([
        InlineKeyboardButton(text="⚙️ Edit", callback_data=f"t:{trade_id}:edit:{ctx}"),
        InlineKeyboardButton(text="🔄 Price", callback_data=f"t:{trade_id}:refresh:{ctx}"),
    ])
    rows.append([
        InlineKeyboardButton(text="📤 Market close", callback_data=f"t:{trade_id}:ask_market:{ctx}"),
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"t:{trade_id}:ask_cancel:{ctx}"),
    ])
    rows.append([
        InlineKeyboardButton(text="◀ My trades", callback_data=f"mt:{period}:{page}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_trade_detail_kb(
    trade_id: int,
    period: str,
    page: int,
    setup_url: str | None,
    *,
    show_history: bool = False,
    trades: list | None = None,
) -> InlineKeyboardMarkup:
    ctx = _trade_ctx(period, page)
    rows: list[list[InlineKeyboardButton]] = []
    if setup_url:
        rows.append([InlineKeyboardButton(text="📎 Open setup", url=setup_url)])
    if trades:
        nav = _trade_neighbor_row(
            trade_id,
            trades,
            make_callback=lambda tid: f"t:{tid}:open:{ctx}",
        )
        if nav:
            rows.append(nav)
    if show_history:
        rows.append([
            InlineKeyboardButton(text="📜 History", callback_data=f"t:{trade_id}:history:{ctx}"),
        ])
    rows.append([
        InlineKeyboardButton(text="◀ My trades", callback_data=f"mt:{period}:{page}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trader_detail_kb(user_id: int, period, trades, page: int = 0) -> InlineKeyboardMarkup:
    page_trades, page, total_pages = paginate_trader_trades(trades, page)
    rows = [
        [InlineKeyboardButton(
            text=format_trader_trade_line(t),
            callback_data=f"tt:{t.id}:{user_id}:{period.value}:{page}",
        )]
        for t in page_trades
    ]
    rows.extend(_trader_trades_page_nav(user_id, period, page, total_pages))
    rows.append([
        InlineKeyboardButton(text="◀ Leaderboard", callback_data=f"lb:{period.value}:0"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_detail_kb(
    trade_id: int,
    user_id: int,
    period,
    setup_url: str | None,
    trades: list | None = None,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    rows = []
    if setup_url:
        rows.append([InlineKeyboardButton(text="📎 Open setup", url=setup_url)])
    if trades:
        nav = _trade_neighbor_row(
            trade_id,
            trades,
            make_callback=lambda tid: f"tt:{tid}:{user_id}:{period.value}:{page}",
        )
        if nav:
            rows.append(nav)
    rows.append([
        InlineKeyboardButton(
            text="◀ Back to trades",
            callback_data=f"tr:{user_id}:{period.value}:{page}",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pts_lb(v: float) -> str:
    return f"{v:.2f}"


def format_trader_trade_line(trade) -> str:
    sym = trade.symbol.replace("USDT", "")
    side = trade.side.value.upper()
    num = trade.user_trade_number or trade.id
    if trade.status == TradeStatus.CANCELLED:
        return f"#{num} {sym} {side} — Cancelled"
    pts = trade.result_points or 0
    return f"#{num} {sym} {side} ({_pts_lb(pts)})"


STATUS_LABELS = {
    TradeStatus.PLANNED: "Planned",
    TradeStatus.PENDING: "Pending",
    TradeStatus.OPEN: "Open",
    TradeStatus.PARTIALLY_CLOSED: "Partially closed",
    TradeStatus.CLOSED: "Closed",
    TradeStatus.CANCELLED: "Cancelled",
}

ENTRY_LABELS = {
    EntryType.MARKET: "Market",
    EntryType.LIMIT: "Limit",
    EntryType.OPEN: "Open",
}
