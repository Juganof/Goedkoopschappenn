import pytest
from src.app import format_price, format_unit_size, format_price_per_unit

@pytest.mark.parametrize("input_price,expected", [
    # Common Dutch price formats
    ("€10.50", "10,50"),
    ("€1,99", "1,99"),
    ("10.50", "10,50"),
    ("1,99", "1,99"),
    # Edge cases
    ("€0,00", "0,00"),
    ("€0.00", "0,00"),
    ("invalid", "0,00"),
    (None, "0,00")
])
def test_format_price(input_price, expected):
    assert format_price(input_price) == expected

@pytest.mark.parametrize("input_size,expected", [
    # Common Dutch unit sizes
    ("2 stuk", "2 stuks"),
    ("1 stuk", "1 stuks"),
    ("500g", "500 g"),
    ("1kg", "1 kg"),
    ("1500g", "1.5 kg"),
    # Per unit prices
    ("per 100 gram", "Per 100 g"),
    ("per 1 kg", "Per 1 kg"),
    ("per stuk", "Per stuk"),
    # Package sizes
    ("6x500g", "6x500 g"),
    ("multipack 4x125g", "4x125 g"),
    # Edge cases
    ("", ""),
    (None, "")
])
def test_format_unit_size(input_size, expected):
    assert format_unit_size(input_size) == expected

@pytest.mark.parametrize("price,unit_size,expected", [
    # Per piece pricing
    (5.00, "2 stuk", "€2,50/stuk"),
    (3.00, "3 stuks", "€1,00/stuk"),
    # Weight-based pricing
    (5.00, "500g", "€10,00/kg"),
    (10.00, "1kg", "€10,00/kg"),
    (3.00, "250g", "€12,00/kg"),
    # Multipack pricing
    (6.00, "6x500g", "€2,00/kg"),
    (4.00, "4x125g", "€8,00/kg"),
    # Edge cases
    (None, "500g", ""),
    (5.00, None, ""),
    (5.00, "invalid", "€5,00"),
    (5.00, "", "€5,00")
])
def test_format_price_per_unit(price, unit_size, expected):
    assert format_price_per_unit(price, unit_size) == expected 