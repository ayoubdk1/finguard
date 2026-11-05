
from decimal import Decimal, InvalidOperation

CURRENCY_EXPONENTS: dict[str, int] = {
    "TND": 3,
    "USD": 2,
    "EUR": 2,
}

SUPPORTED_CURRENCIES = tuple(CURRENCY_EXPONENTS.keys())


def get_currency_exponent(currency: str) -> int:
    if not isinstance(currency, str):
        raise ValueError("Currency must be a string")

    normalized_currency = currency.strip().upper()

    if normalized_currency not in CURRENCY_EXPONENTS:
        raise ValueError(f"Unsupported currency: {normalized_currency}")

    return CURRENCY_EXPONENTS[normalized_currency]


def to_minor_units(amount: str, currency: str) -> int:
    """Convert a positive decimal string into integer minor units."""
    exponent = get_currency_exponent(currency)

    if not isinstance(amount, str):
        raise ValueError("Amount must be provided as a decimal string")

    try:
        decimal_amount = Decimal(amount)
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid monetary amount") from None

    if not decimal_amount.is_finite() or decimal_amount <= 0:
        raise ValueError("Amount must be a positive finite number")

    minor_amount = decimal_amount * (Decimal(10) ** exponent)

    if minor_amount != minor_amount.to_integral_value():
        normalized_currency = currency.strip().upper()
        raise ValueError(
            f"{normalized_currency} supports only {exponent} decimal places"
        )

    return int(minor_amount)


def from_minor_units(amount_minor_units: int, currency: str) -> Decimal:
    """Convert integer minor units into a Decimal with the correct scale."""
    exponent = get_currency_exponent(currency)

    if isinstance(amount_minor_units, bool) or not isinstance(amount_minor_units, int):
        raise ValueError("Minor-unit amount must be an integer")

    scale = Decimal(10) ** exponent

    return (Decimal(amount_minor_units) / scale).quantize(
        Decimal(1).scaleb(-exponent)
    )
