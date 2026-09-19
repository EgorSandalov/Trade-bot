import pytest

from bot.domain.numbers import format_price, parse_number


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0,5", 0.5),
        ("0,049", 0.049),
        ("0,052", 0.052),
        ("0.5", 0.5),
        ("10,50", 10.5),
        ("96000", 96000.0),
        ("96,000", 96000.0),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value,expected",
    [
        (104.82, "104.82"),
        (118.71, "118.71"),
        (111.0, "111"),
        (96000.0, "96000"),
        (0.049, "0.049"),
    ],
)
def test_format_price(value, expected):
    assert format_price(value) == expected
