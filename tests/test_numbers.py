import pytest

from bot.domain.numbers import parse_number


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0,5", 0.5),
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
