"""Formato de montos enteros en unidad mínima."""

from decimal import ROUND_HALF_UP, Decimal

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


def format_change(amount: int, base: int, currency: str) -> str:
    """Variación de `base` a `amount` en plata y en porcentaje: "-$1.000 (-10 %)".

    El porcentaje se calcula con `Decimal` (un decimal, sin ",0"; "<0,1 %" si redondea a
    cero) y se omite si la base no es positiva. Sin cambio da "sin cambio". El texto no
    lleva caracteres HTML sin escapar salvo "<" en "<0,1": quien lo use en HTML lo escapa.
    """
    diff = amount - base
    if diff == 0:
        return "sin cambio"
    text = ("+" if diff > 0 else "") + format_price(diff, currency)
    if base > 0:
        pct = (Decimal(diff) * 100 / Decimal(base)).quantize(Decimal("0.1"), ROUND_HALF_UP)
        # Un cambio real menor a 0,05 % redondea a cero: "+0 %" confundiría.
        pct_text = "<0,1" if pct == 0 else f"{pct:+}".replace(".", ",").removesuffix(",0")
        text += f" ({pct_text} %)"
    return text
