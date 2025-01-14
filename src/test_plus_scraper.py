import asyncio
import json
from plus_scraper import scrape_plus_products

async def test_scraper():
    products = await scrape_plus_products('kaas')
    if not products:
        print("No products found!")
        return
        
    # Print first 3 products with their links
    print("\nFirst 3 products:")
    for i, product in enumerate(products[:3], 1):
        print(f"\n{i}. {product.get('name', 'Unknown')}")
        print(f"   Link: {product.get('link', 'No link')}")
        print(f"   Price: €{product.get('price', 0.0)}")
        print(f"   Brand: {product.get('brand', 'Unknown')}")
        print(f"   Unit: {product.get('unit_size', 'Unknown')}")

if __name__ == "__main__":
    asyncio.run(test_scraper()) 