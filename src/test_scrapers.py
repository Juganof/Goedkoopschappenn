import asyncio
from ah_scraper import scrape_ah_products
from jumbo_scraper import scrape_jumbo_products
from plus_scraper import scrape_plus_products
import json

async def test_scrapers():
    search_term = "kaas"  # Test with cheese products
    print(f"\nTesting scrapers with search term: {search_term}\n")
    
    # Test AH scraper (async)
    print("Testing AH scraper...")
    try:
        ah_products = await scrape_ah_products(search_term)
        print(f"Found {len(ah_products)} AH products")
    except Exception as e:
        print(f"Error with AH scraper: {str(e)}")
    
    # Test Jumbo scraper (async)
    print("\nTesting Jumbo scraper...")
    try:
        jumbo_products = await scrape_jumbo_products(search_term)
        print(f"Found {len(jumbo_products)} Jumbo products")
    except Exception as e:
        print(f"Error with Jumbo scraper: {str(e)}")
    
    # Test Plus scraper (async)
    print("\nTesting Plus scraper...")
    try:
        plus_products = await scrape_plus_products(search_term)
        print(f"Found {len(plus_products)} Plus products")
    except Exception as e:
        print(f"Error with Plus scraper: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_scrapers()) 