import asyncio
from scrapling.defaults import StealthyFetcher
import json
import os
from datetime import datetime, timedelta
import re
import random
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cache settings
CACHE_DIR = Path("cache")
CACHE_DURATION = timedelta(hours=12)  # Base cache duration
CACHE_DURATION_VARIANCE = timedelta(hours=4)  # Random variance to spread updates

def get_cache_file(search_term: str) -> Path:
    """Get the cache file path for a search term"""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"ah_{search_term.lower().replace(' ', '_')}_cache.json"

def should_update_cache(cache_file: Path) -> bool:
    """Check if the cache should be updated"""
    if not cache_file.exists():
        return True
        
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            
        # Get the cache timestamp
        cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
        
        # Add random variance to cache duration
        variance = random.uniform(-CACHE_DURATION_VARIANCE.total_seconds(), 
                                CACHE_DURATION_VARIANCE.total_seconds())
        actual_duration = CACHE_DURATION + timedelta(seconds=variance)
        
        # Check if cache has expired
        return datetime.now() - cache_time > actual_duration
        
    except Exception as e:
        logger.error(f"Error reading cache: {str(e)}")
        return True

def save_to_cache(search_term: str, products: list) -> None:
    """Save products to cache"""
    cache_file = get_cache_file(search_term)
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'products': products
    }
    
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(products)} products to cache for '{search_term}'")
    except Exception as e:
        logger.error(f"Error saving to cache: {str(e)}")

def load_from_cache(search_term: str) -> list:
    """Load products from cache"""
    cache_file = get_cache_file(search_term)
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        products = cache_data.get('products', [])
        logger.info(f"Loaded {len(products)} products from cache for '{search_term}'")
        return products
    except Exception as e:
        logger.error(f"Error loading from cache: {str(e)}")
        return None

def save_debug_html(html_content, search_term):
    """Save HTML content to a debug file."""
    debug_dir = "debug"
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
    
    debug_file = os.path.join(debug_dir, f"ah_search_{search_term}_{len(os.listdir(debug_dir))}.html")
    with open(debug_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Debug HTML saved to: {debug_file}")

async def scrape_ah_products(search_term):
    """
    Scrapes products from Albert Heijn for a given search term using Scrapling.
    Returns a list of products sorted by price.
    """
    logger.info(f"Starting product search for: {search_term}")
    
    # Check cache first
    cache_file = get_cache_file(search_term)
    if not should_update_cache(cache_file):
        cached_products = load_from_cache(search_term)
        if cached_products is not None:
            return cached_products
    
    logger.info(f"Cache needs update, scraping fresh data for: {search_term}")
    
    try:
        # Navigate to search results
        url = f"https://www.ah.nl/zoeken?query={search_term}"
        print(f"Navigating to {url}")
        
        # Use StealthyFetcher to get the page
        page = await StealthyFetcher.async_fetch(
            url,
            headless=True,
            network_idle=True,
            wait_selector='[data-testhook="product-card"]',
            disable_resources=True,
            timeout=90000  # Increased timeout
        )
        
        print("Extracting product information...")
        products = []
        
        # Find all product cards
        product_cards = page.css('[data-testhook="product-card"]')
        print(f"Found {len(product_cards)} product cards")
        
        for card in product_cards:
            try:
                # Get product name
                name_element = card.css_first('[data-testhook="product-title-line-clamp"]')
                if not name_element:
                    continue
                name = name_element.text.strip()
                print(f"\nProcessing product: {name}")
                
                # Get price
                price_element = card.css_first('[data-testhook="price-amount"]')
                if not price_element:
                    print(f"No price found for product: {name}")
                    continue
                integer_part = price_element.css_first('.price-amount_integer__\\+e2XO').text
                fractional_part = price_element.css_first('.price-amount_fractional__kjJ7u').text
                price = float(f"{integer_part}.{fractional_part}")
                price_display = f"€{price:.2f}"
                print(f"Found price: {price_display}")
                
                # Check for bonus/promotional price
                is_bonus = False
                original_price = None
                original_price_display = None
                bonus_price = None
                bonus_price_display = None
                
                # Look for bonus price elements
                bonus_element = card.css_first('[class*="price-promotion"]')
                if bonus_element:
                    is_bonus = True
                    # The current price is the bonus price
                    bonus_price = price
                    bonus_price_display = price_display
                    
                    # Try to find original price
                    original_price_element = card.css_first('[class*="price-promotion"] [class*="strike"]')
                    if original_price_element:
                        try:
                            original_price_text = original_price_element.text.strip().replace('€', '').replace(',', '.')
                            original_price = float(original_price_text)
                            original_price_display = f"€{original_price:.2f}"
                        except:
                            pass
                
                # Get unit size (e.g., "400 g", "1 kg")
                unit_size_element = card.css_first('[data-testhook="product-unit-size"]')
                unit_size = unit_size_element.text.strip() if unit_size_element else None
                
                # Convert unit size to standard format if possible
                if unit_size:
                    match = re.search(r'(\d+)\s*([gk]|kg|gram|stuk)(?:[^a-z]|$)', unit_size.lower())
                    if match:
                        num = match.group(1)
                        unit = match.group(2).lower()
                        if unit in ['g', 'gram']:
                            unit_size = f"{num}g"
                        elif unit in ['k', 'kg']:
                            unit_size = f"{int(num) * 1000}g"
                        elif unit == 'stuk':
                            unit_size = f"{num} stuk"
                
                # Get unit price (price per kg/liter)
                unit_price_element = card.css_first('[data-testhook="price-amount-per-unit"]')
                unit_price = None
                unit_price_display = None
                if unit_price_element:
                    try:
                        unit_price_text = unit_price_element.text.strip()
                        # Clean up unit price text (e.g., "€ 13.98 / kg" -> 13.98)
                        unit_price = float(unit_price_text.split('/')[0].replace('€', '').strip())
                        unit_price_display = unit_price_text.strip()
                    except:
                        pass
                
                # Get image
                img_element = card.css_first('[data-testhook="product-image"]')
                if not img_element:
                    print(f"No image found for product: {name}")
                    continue
                image = img_element.attrib.get('src', '')
                if not image:
                    print(f"No image URL found for product: {name}")
                    continue
                
                # Get link
                link_element = card.css_first('a[href^="/producten/product"]')
                if not link_element:
                    print(f"No link found for product: {name}")
                    continue
                link = "https://www.ah.nl" + link_element.attrib.get('href', '')
                
                # Get product properties (e.g., "Vega", "Biologisch")
                properties = []
                properties_element = card.css_first('[data-testhook="product-properties"]')
                if properties_element:
                    for prop in properties_element.css('svg'):
                        prop_title = prop.css_first('title')
                        if prop_title:
                            properties.append(prop_title.text.strip())
                
                # Get nutriscore if available
                nutriscore = None
                nutriscore_element = card.css_first('[data-testhook="product-highlight"]')
                if nutriscore_element and 'nutriscore' in nutriscore_element.attrib.get('class', ''):
                    for class_name in nutriscore_element.attrib.get('class', '').split():
                        if 'nutriscore-' in class_name:
                            nutriscore = class_name[-1].upper()
                            break
                
                # Get product ID from URL
                product_id = None
                if link:
                    id_match = re.search(r'/product/(\d+)/?', link)
                    if id_match:
                        product_id = id_match.group(1)
                
                # Get brand (if available)
                brand_element = card.css_first('[data-testhook="product-brand"]')
                brand = brand_element.text.strip() if brand_element else None
                
                # Get stock status
                stock_element = card.css_first('[data-testhook="product-stock"]')
                stock_status = stock_element.text.strip().lower() if stock_element else 'in stock'
                
                products.append({
                    'id': product_id,
                    'name': name,
                    'brand': brand,
                    'price': price,
                    'price_display': price_display,
                    'is_bonus': is_bonus,
                    'original_price': original_price,
                    'original_price_display': original_price_display,
                    'bonus_price': bonus_price,
                    'bonus_price_display': bonus_price_display,
                    'unit_size': unit_size,
                    'unit_price': unit_price,
                    'unit_price_display': unit_price_display,
                    'image': image,
                    'link': link,
                    'properties': properties,
                    'nutriscore': nutriscore,
                    'stock_status': stock_status,
                    'store': 'ah',
                    'scraped_at': datetime.now().isoformat()
                })
                
            except Exception as e:
                print(f"Error processing product: {str(e)}")
                continue
        
        # Sort products by price
        products.sort(key=lambda x: x['price'])
        
        # After successful scraping, save to cache
        if products:
            save_to_cache(search_term, products)
        
        print(f"Successfully extracted {len(products)} products")
        return products
        
    except Exception as e:
        print(f"Error scraping products: {str(e)}")
        raise

if __name__ == "__main__":
    # Test the scraper
    products = asyncio.run(scrape_ah_products("kaas"))
    with open('cheese_products.json', 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2) 