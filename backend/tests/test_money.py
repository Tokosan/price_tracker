import pytest

from tracker.money import format_change


@pytest.mark.parametrize(
    ("amount", "base", "currency", "expected"),
    [
        (9000, 10000, "CLP", "-$1.000 (-10 %)"),
        (12000, 10000, "CLP", "+$2.000 (+20 %)"),
        (249966, 248803, "CLP", "+$1.163 (+0,5 %)"),
        (8000, 9000, "CLP", "-$1.000 (-11,1 %)"),
        (10000, 10000, "CLP", "sin cambio"),
        (100, 0, "CLP", "+$100"),  # base 0: sin porcentaje
        (1999, 3000, "USD", "-US$10,01 (-33,4 %)"),
    ],
)
def test_format_change(amount, base, currency, expected):
    assert format_change(amount, base, currency) == expected
