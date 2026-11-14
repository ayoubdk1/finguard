from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currencies import CURRENCY_EXPONENTS
from app.db.models import ExchangeRate


class FXError(Exception):
    """Base exception for foreign exchange errors."""
    pass


class ExchangeRateNotFound(FXError):
    pass


def get_latest_rate(
    session: Session,
    base_currency: str,
    target_currency: str,
) -> ExchangeRate:
    if base_currency == target_currency:
        raise FXError("Source and target currencies are identical")

    rate = session.scalar(
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == base_currency,
            ExchangeRate.target_currency == target_currency,
        )
        .order_by(ExchangeRate.created_at.desc())
    )
    if rate is None:
        raise ExchangeRateNotFound(
            f"No exchange rate found for {base_currency} -> {target_currency}"
        )
    return rate


def calculate_fx_conversion(
    source_amount_cents: int,
    base_currency: str,
    target_currency: str,
    rate_scaled: int,
    fee_bps: int = 50,
) -> tuple[int, int, Decimal]:
    """
    Deterministically converts source_amount_cents from base to target currency.
    Returns:
        (destination_amount_cents, fee_in_source_cents, effective_rate)
    """
    src_decimals = CURRENCY_EXPONENTS[base_currency]
    dst_decimals = CURRENCY_EXPONENTS[target_currency]

    # Convert rate back from fixed-point (scaled by 1,000,000)
    rate_dec = Decimal(rate_scaled) / Decimal(1_000_000)

    # Calculate fee (e.g. 50 bps = 0.005)
    fee_ratio = Decimal(fee_bps) / Decimal(10_000)
    fee_in_source_cents = int((Decimal(source_amount_cents) * fee_ratio).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))

    net_source_cents = source_amount_cents - fee_in_source_cents
    if net_source_cents <= 0:
        raise FXError("Transfer amount is too small to cover exchange fee")

    # Major unit of source currency
    net_source_major = Decimal(net_source_cents) / Decimal(10 ** src_decimals)

    # Converted major unit in target currency
    target_major = net_source_major * rate_dec

    # Convert back to target minor units
    destination_amount_cents = int((target_major * Decimal(10 ** dst_decimals)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))

    return destination_amount_cents, fee_in_source_cents, rate_dec
