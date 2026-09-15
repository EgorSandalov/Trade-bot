from bot.domain.enums import Period
from bot.keyboards.menus import (
    LEADERBOARD_PAGE_SIZE,
    TRADER_TRADES_PAGE_SIZE,
    paginate_leaderboard,
    paginate_trader_trades,
)


def _entries(n: int):
    return list(range(n))


def test_leaderboard_pagination_six_per_page():
    entries = _entries(14)
    for period in (Period.ALL, Period.MONTH, Period.WEEK, Period.DAY):
        page_entries, page, total_pages = paginate_leaderboard(entries, period, 0)
        assert len(page_entries) == LEADERBOARD_PAGE_SIZE
        assert page == 0
        assert total_pages == 3

        page_entries, page, total_pages = paginate_leaderboard(entries, period, 2)
        assert len(page_entries) == 2
        assert page == 2
        assert total_pages == 3


def test_leaderboard_no_pagination_when_fits():
    entries = _entries(4)
    page_entries, page, total_pages = paginate_leaderboard(entries, Period.MONTH, 0)
    assert page_entries == entries
    assert page == 0
    assert total_pages == 1


def test_trader_trades_pagination_six_per_page():
    trades = _entries(13)
    page_trades, page, total_pages = paginate_trader_trades(trades, 1)
    assert len(page_trades) == TRADER_TRADES_PAGE_SIZE
    assert page == 1
    assert total_pages == 3
    assert page_trades[0] == TRADER_TRADES_PAGE_SIZE
