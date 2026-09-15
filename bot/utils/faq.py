from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup



from bot.domain.exchanges import exchanges_list



MAX_FAQ_LEN = 4096





def faq_language_kb() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(inline_keyboard=[

        [

            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="faq:ru:0"),

            InlineKeyboardButton(text="🇬🇧 English", callback_data="faq:en:0"),

        ],

    ])





def faq_page_kb(lang: str, page: int, total: int) -> InlineKeyboardMarkup:

    nav: list[InlineKeyboardButton] = []

    if page > 0:

        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"faq:{lang}:{page - 1}"))

    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="faq:noop"))

    if page < total - 1:

        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"faq:{lang}:{page + 1}"))



    switch = (

        ("🇬🇧 English", f"faq:en:{page}") if lang == "ru" else ("🇷🇺 Русский", f"faq:ru:{page}")

    )

    rows = [nav] if nav else []

    rows.append([InlineKeyboardButton(text=switch[0], callback_data=switch[1])])

    return InlineKeyboardMarkup(inline_keyboard=rows)





def faq_picker_text() -> str:

    return (

        "<b>📘 FAQ</b>\n\n"

        "Выберите язык / Choose language:"

    )





def faq_page_count(lang: str) -> int:

    return len(_faq_pages(lang))





def format_faq_page(lang: str, page: int) -> str:

    pages = _faq_pages(lang)

    page = max(0, min(page, len(pages) - 1))

    text = pages[page]

    if len(text) <= MAX_FAQ_LEN:

        return text

    return text[: MAX_FAQ_LEN - 20] + "\n\n<i>…</i>"





def format_faq_text(lang: str = "ru", page: int = 0) -> str:

    return format_faq_page(lang, page)





def format_faq(lang: str = "ru") -> list[str]:

    return _faq_pages(lang)





def _faq_pages(lang: str) -> list[str]:

    return _faq_ru_pages() if lang == "ru" else _faq_en_pages()





def _faq_ru_pages() -> list[str]:

    ex = exchanges_list()

    return [

        (

            "<b>📘 FAQ · 1/6</b>\n\n"

            "<b>Где что делать</b>\n"

            "Setups — новый сетап · General — /trades, /leaderboard\n\n"

            "<b>Формат</b> одна строка = одно поле, English.\n"

            f"Биржи: {ex} (HL/HYPE = Hyperliquid)\n\n"

            "<b>Type</b> market · limit · open\n"

            "market — без Entry · limit/open — Entry обязателен\n\n"

            "<b>Уровни</b> (разделители: пробел, запятая, тире)\n"

            "<pre>TP1: 96000 - 50%\n"

            "SL: 93000\n"

            "SL: trail 0,5%\n"

            "SL: 75000\n"

            "SL: trail 0,5% - 80000</pre>\n"

            "Дробные: 0,5 или 0.5 · TP сумма ≤ 100%\n"

            "Trailing — стр. 3 · примеры — стр. 2 и 4\n\n"

            "Фото с текстом в подписи — OK."

        ),

        (

            "<b>📘 FAQ · 2/6</b>\n\n"

            "<b>Market LONG</b>\n"

            "<pre>MEXC\nBTC\nLONG\nType: market\nLeverage: 100\n"

            "SL: 80000\nTP1: 85000 - 100%</pre>\n\n"

            "<b>Market SHORT</b>\n"

            "<pre>OKX\nETH\nSHORT\nType: market\nLeverage: 20\n"

            "SL: 3500\nTP1: 3200 - 50%\nTP2: 3000 - 50%</pre>\n\n"

            "<b>Market + Comment</b>\n"

            "<pre>Bybit\nSOL\nLONG\nType: market\nLeverage: 10\n"

            "SL: 180\nTP1: 200 - 100%\nComment: breakout retest</pre>"

        ),

        (

            "<b>📘 FAQ · 3/6</b>\n\n"

            "<b>Trailing Stop</b>\n"

            "SL следует за ценой в выгодную сторону (1m-свечи)\n\n"

            "<b>С активацией</b> — нужен фикс. SL до неё:\n"

            "<pre>SL: 75000\n"

            "SL: trail 0,5% - 80000</pre>\n"

            "Или одной строкой: <code>SL: trail 0,5% - 80000 stop 75000</code>\n\n"

            "<b>Без активации</b>\n"

            "<pre>SL: trail 3%</pre>\n\n"

            "<b>Пример</b>\n"

            "<pre>OKX\nBTC\nLONG\nType: market\nLeverage: 10\n"

            "SL: 74000\n"

            "SL: trail 0,5% - 80000\n"

            "TP1: 85000 - 50%\nTP2: 90000 - 50%</pre>\n\n"

            "<b>Биржи</b>\n"

            "OKX · Bybit · BingX · MEXC\n"

            "  → trailing + активация + фикс. SL\n\n"

            "Binance · Bitget\n"

            "  → trailing % + активация\n\n"

            "Hyperliquid (HL)\n"

            "  → только фикс. SL"

        ),

        (

            "<b>📘 FAQ · 4/6</b>\n\n"

            "<b>Limit LONG</b>\n"

            "<pre>OKX\nBTC\nLONG\nType: limit\nLeverage: 10\n"

            "Entry: 95000\nSL: 93000\nTP1: 96000 - 50%\nTP2: 97000 - 50%</pre>\n\n"

            "<b>Limit SHORT</b>\n"

            "<pre>Binance\nBTC\nSHORT\nType: limit\nLeverage: 25\n"

            "Entry: 90000\nSL: 92000\nTP1: 88000 - 100%</pre>\n\n"

            "<b>Open</b>\n"

            "<pre>OKX\nBTC\nLONG\nType: open\nLeverage: 5\n"

            "Entry: 94500\nSL: 93000\nTP1: 96000 - 100%</pre>"

        ),

        (

            "<b>📘 FAQ · 5/6</b>\n\n"

            "<b>После публикации</b> ✅ Trade #N → General → /trades\n\n"

            "<b>Редактирование</b> /trades → ⚙️ Edit\n"

            "Шаблон → правки текстом → сообщение удалится\n\n"

            "SL/TP проверяются по 1m-свечам (~7 сек).\n"

            "Не менять: биржу, пару, LONG/SHORT, Type.\n"

            "TP уже сработал — только Remaining %.\n"

            "SL может быть выше Entry (breakeven), если ниже рынка.\n\n"

            "<pre>Reason: опционально</pre>\n\n"

            "<b>Закрытие</b> 📤 Market close — остаток по рынку\n"

            "<b>Отмена</b> ❌ Cancel"

        ),

        (

            "<b>📘 FAQ · 6/6</b>\n\n"

            "<b>Профиль</b> /myprofile — banner, stickers (+100% / -100%)\n"

            "<b>Лидерборд</b> /leaderboard — месяц по умолчанию\n\n"

            "<b>Команды</b>\n"

            "/faq\n/trades\n/leaderboard\n/myprofile\n/help\n/chat_id\n/myid\n\n"

            "<b>Баллы</b>\n"

            "<pre>points = clean + personal / 20\n"

            "personal = clean × leverage\n"

            "Breakeven (0 … +0.2%): −1\n"

            "Малый минус (−1 … 0%): −1 + personal / 20</pre>\n\n"

            "<b>Автозакрытие</b> 1m-свечи (~7 сек), после простоя — replay истории."

        ),

    ]





def _faq_en_pages() -> list[str]:

    ex = exchanges_list()

    return [

        (

            "<b>📘 FAQ · 1/6</b>\n\n"

            "<b>Where</b> Setups — new setup · General — /trades, /leaderboard\n\n"

            "<b>Format</b> one field per line, English.\n"

            f"Exchanges: {ex}\n\n"

            "<b>Type</b> market · limit · open\n"

            "market — no Entry · limit/open — Entry required\n\n"

            "<b>Levels</b> (separators: space, comma, dash)\n"

            "<pre>TP1: 96000 - 50%\n"

            "SL: 93000\n"

            "SL: trail 0.5%\n"

            "SL: 75000\n"

            "SL: trail 0.5% - 80000</pre>\n"

            "Decimals: 0.5 or 0,5 · TP sum ≤ 100%\n"

            "Trailing — p. 3 · examples — p. 2 & 4\n\n"

            "Chart photo with caption — OK."

        ),

        (

            "<b>📘 FAQ · 2/6</b>\n\n"

            "<b>Market LONG</b>\n"

            "<pre>MEXC\nBTC\nLONG\nType: market\nLeverage: 100\n"

            "SL: 80000\nTP1: 85000 - 100%</pre>\n\n"

            "<b>Market SHORT</b>\n"

            "<pre>OKX\nETH\nSHORT\nType: market\nLeverage: 20\n"

            "SL: 3500\nTP1: 3200 - 50%\nTP2: 3000 - 50%</pre>\n\n"

            "<b>Market + Comment</b>\n"

            "<pre>Bybit\nSOL\nLONG\nType: market\nLeverage: 10\n"

            "SL: 180\nTP1: 200 - 100%\nComment: breakout retest</pre>"

        ),

        (

            "<b>📘 FAQ · 3/6</b>\n\n"

            "<b>Trailing Stop</b>\n"

            "SL follows price in the profitable direction (1m candles)\n\n"

            "<b>With activation</b> — fixed SL required until then:\n"

            "<pre>SL: 75000\n"

            "SL: trail 0.5% - 80000</pre>\n"

            "Or one line: <code>SL: trail 0.5% - 80000 stop 75000</code>\n\n"

            "<b>Without activation</b>\n"

            "<pre>SL: trail 3%</pre>\n\n"

            "<b>Example</b>\n"

            "<pre>OKX\nBTC\nLONG\nType: market\nLeverage: 10\n"

            "SL: 74000\n"

            "SL: trail 0.5% - 80000\n"

            "TP1: 85000 - 50%\nTP2: 90000 - 50%</pre>\n\n"

            "<b>Exchanges</b>\n"

            "OKX · Bybit · BingX · MEXC\n"

            "  → trailing + activation + fixed SL\n\n"

            "Binance · Bitget\n"

            "  → trailing % + activation\n\n"

            "Hyperliquid (HL)\n"

            "  → fixed SL only"

        ),

        (

            "<b>📘 FAQ · 4/6</b>\n\n"

            "<b>Limit LONG</b>\n"

            "<pre>OKX\nBTC\nLONG\nType: limit\nLeverage: 10\n"

            "Entry: 95000\nSL: 93000\nTP1: 96000 - 50%\nTP2: 97000 - 50%</pre>\n\n"

            "<b>Limit SHORT</b>\n"

            "<pre>Binance\nBTC\nSHORT\nType: limit\nLeverage: 25\n"

            "Entry: 90000\nSL: 92000\nTP1: 88000 - 100%</pre>\n\n"

            "<b>Open</b>\n"

            "<pre>OKX\nBTC\nLONG\nType: open\nLeverage: 5\n"

            "Entry: 94500\nSL: 93000\nTP1: 96000 - 100%</pre>"

        ),

        (

            "<b>📘 FAQ · 5/6</b>\n\n"

            "<b>After posting</b> ✅ Trade #N → General → /trades\n\n"

            "<b>Edit</b> /trades → ⚙️ Edit — template, edit, message deleted\n\n"

            "SL/TP checked via 1m candles (~7s).\n"

            "Do not change: exchange, pair, direction, Type.\n"

            "SL may be above Entry (breakeven) if below market.\n\n"

            "<pre>Reason: optional</pre>\n\n"

            "<b>Close</b> 📤 Market close — remaining size at market\n"

            "<b>Cancel</b> ❌ Cancel"

        ),

        (

            "<b>📘 FAQ · 6/6</b>\n\n"

            "<b>Profile</b> /myprofile — banner, stickers (+100% / -100%)\n"

            "<b>Leaderboard</b> /leaderboard — month default\n\n"

            "<b>Commands</b>\n"

            "/faq\n/trades\n/leaderboard\n/myprofile\n/help\n/chat_id\n/myid\n\n"

            "<b>Points</b>\n"

            "<pre>points = clean + personal / 20\n"

            "personal = clean × leverage\n"

            "Breakeven (0 … +0.2%): −1\n"

            "Small loss (−1 … 0%): −1 + personal / 20</pre>\n\n"

            "<b>Auto-close</b> 1m candles (~7s); after downtime — history replay."

        ),

    ]

