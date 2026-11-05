
import pytest
from decimal import Decimal

from app.core.currencies import (
    to_minor_units,
    from_minor_units,
    SUPPORTED_CURRENCIES,
)


def test_tnd_conversion():
    assert to_minor_units("12.500", "TND") == 12500


def test_usd_conversion():
    assert to_minor_units("12.50", "USD") == 1250


def test_eur_conversion():
    assert to_minor_units("12.50", "EUR") == 1250


def test_supported_currencies():
    assert SUPPORTED_CURRENCIES == ("TND", "USD", "EUR")


def test_jpy_is_rejected():
    with pytest.raises(ValueError, match="Unsupported currency"):
        to_minor_units("12", "JPY")


def test_tnd_rejects_excess_precision():
    with pytest.raises(ValueError):
        to_minor_units("12.5001", "TND")


def test_usd_rejects_excess_precision():
    with pytest.raises(ValueError):
        to_minor_units("12.501", "USD")


def test_eur_rejects_excess_precision():
    with pytest.raises(ValueError):
        to_minor_units("12.501", "EUR")


def test_conversion_back_to_major_units():
    assert from_minor_units(12500, "TND") == Decimal("12.500")
    assert from_minor_units(1250, "USD") == Decimal("12.50")
    assert from_minor_units(1250, "EUR") == Decimal("12.50")


def test_currency_is_case_insensitive():
    assert to_minor_units("12.50", "eur") == 1250


def test_boolean_is_not_a_valid_minor_unit_amount():
    with pytest.raises(ValueError):
        from_minor_units(True, "USD")
