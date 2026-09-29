"""Formato de montos enteros en unidad mínima."""

from tracker.processors.util import exponent

_SYMBOLS = {"CLP": "$", "USD": "US$", "EUR": "€"}


def format_price(amount: int | None, currency: str) -> str:
    if amount is None:
        return "sin precio"
    exp = exponent(currency)
    symbol = _SYMBOLS.get(currency.upper(), currency.upper() + " ")
    whole, frac = divmod(abs(amount), 10**exp) if exp else (abs(amount), 0)
    text = f"{whole:,}".replace(",", ".")
    if exp:
        text += "," + str(frac).zfill(exp)
    return f"{'-' if amount < 0 else ''}{symbol}{text}"
