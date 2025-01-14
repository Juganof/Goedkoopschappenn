import pytest
import asyncio
from src.ah_scraper import scrape_ah_products
from src.jumbo_scraper import scrape_jumbo_products
from src.plus_scraper import scrape_plus_products

@pytest.mark.asyncio
async def test_ah_scraper():
    search_term = "kaas"
    products = await scrape_ah_products(search_term)
    assert isinstance(products, list)
    if products:  # Only test if products were found
        assert all(isinstance(p, dict) for p in products)
        assert all('name' in p for p in products)
        assert all('price' in p for p in products)
        assert all('store' in p for p in products)

@pytest.mark.asyncio
async def test_jumbo_scraper():
    search_term = "kaas"
    products = await scrape_jumbo_products(search_term)
    assert isinstance(products, list)
    if products:  # Only test if products were found
        assert all(isinstance(p, dict) for p in products)
        assert all('name' in p for p in products)
        assert all('price' in p for p in products)
        assert all('store' in p for p in products)

@pytest.mark.asyncio
async def test_plus_scraper():
    search_term = "kaas"
    products = await scrape_plus_products(search_term)
    assert isinstance(products, list)
    if products:  # Only test if products were found
        assert all(isinstance(p, dict) for p in products)
        assert all('name' in p for p in products)
        assert all('price' in p for p in products)
        assert all('store' in p for p in products)

@pytest.mark.asyncio
async def test_all_scrapers_concurrent():
    search_term = "kaas"
    tasks = [
        scrape_ah_products(search_term),
        scrape_jumbo_products(search_term),
        scrape_plus_products(search_term)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check that at least one scraper returned results
    assert any(isinstance(r, list) for r in results) 