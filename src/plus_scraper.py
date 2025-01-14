import re
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
import random

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Cache settings
CACHE_DIR = Path("cache")
CACHE_DURATION = timedelta(hours=12)  # Base cache duration
CACHE_DURATION_VARIANCE = timedelta(hours=4)  # Random variance to spread updates

def get_cache_file(search_term: str) -> Path:
    """Get the cache file path for a search term."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"plus_{search_term.lower().replace(' ', '_')}_cache.json"

def should_update_cache(cache_file: Path) -> bool:
    """Check if the cache should be updated."""
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
    """Save products to cache."""
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
    """Load products from cache."""
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

def parse_price_integer(price_str: str) -> int:
    """Parse the integer part of the price."""
    if not price_str or not isinstance(price_str, str):
        return 0
    # Remove any non-numeric characters except dots
    clean_str = ''.join(c for c in price_str if c.isdigit() or c == '.')
    try:
        # Remove trailing dot if present
        clean_str = clean_str.rstrip('.')
        return int(clean_str) if clean_str else 0
    except (ValueError, TypeError):
        return 0

def parse_price_decimal(price_str: str) -> int:
    """Parse the decimal part of the price."""
    if not price_str or not isinstance(price_str, str):
        return 0
    # Remove any non-numeric characters
    clean_str = ''.join(c for c in price_str if c.isdigit())
    try:
        return int(clean_str) if clean_str else 0
    except (ValueError, TypeError):
        return 0

def parse_price(price_integer: str, price_decimal: str) -> float:
    """Combine integer and decimal parts into a single price."""
    try:
        # Clean and parse integer part
        integer_str = ''.join(c for c in price_integer if c.isdigit() or c == '.')
        integer_str = integer_str.rstrip('.')
        integer_val = int(integer_str) if integer_str else 0
        
        # Clean and parse decimal part
        decimal_str = ''.join(c for c in price_decimal if c.isdigit())
        decimal_val = int(decimal_str) if decimal_str else 0
        
        # Combine into final price
        price = float(f"{integer_val}.{decimal_val:02d}")
        logger.debug(f"Parsed price: {price} from integer: {price_integer}, decimal: {price_decimal}")
        return price
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing price: {e} (integer: {price_integer}, decimal: {price_decimal})")
        return 0.0

def extract_unit_size(value: str) -> str:
    """Extract unit size from product title."""
    if not value:
        return ""
        
    # Remove 'Per' prefix if present and clean up
    value = value.lower().strip()
    value = re.sub(r'^per\s+', '', value)
    
    # Handle "Per X" format first
    per_match = re.search(r'(\d+(?:[.,]\d+)?)\s*([gk]|kg|gram)', value)
    if per_match:
        num = per_match.group(1).replace(',', '.')
        unit = per_match.group(2).lower()
        if unit in ['k', 'kg']:
            return f"{int(float(num) * 1000)}g"
        return f"{num}g"
    
    # Handle pieces (stuks)
    stuk_match = re.search(r'(\d+)\s*(?:x\s*)?stuk', value)
    if stuk_match:
        return f"{stuk_match.group(1)} stuk"
    
    # Handle slices (plakken)
    plak_match = re.search(r'(\d+)\s*(?:x\s*)?plak(?:ken)?', value)
    if plak_match:
        return f"{plak_match.group(1)} plakken"
    
    # Handle weight units
    weight_match = re.search(r'(\d+(?:[.,]\d+)?)\s*([gk]|kg|gram)(?:[^a-z]|$)', value)
    if weight_match:
        num = weight_match.group(1).replace(',', '.')
        unit = weight_match.group(2).lower()
        
        # Convert to standard format (grams)
        if unit in ['g', 'gram']:
            return f"{int(float(num))}g"
        if unit in ['k', 'kg']:
            try:
                grams = int(float(num) * 1000)
                return f"{grams}g"
            except (ValueError, TypeError):
                return f"{int(float(num) * 1000)}g"
    
    # Handle special cases
    if any(x in value for x in ['half', '-half', ' half']):
        return '400g'  # Standard half size
        
    # Handle numeric-only values (assume grams)
    numeric_match = re.search(r'^(\d+)$', value)
    if numeric_match:
        return f"{numeric_match.group(1)}g"
    
    return value

def extract_brand(name: str) -> str:
    """Extract brand from product name."""
    if not name:
        return ""
    
    # Common brand prefixes
    known_brands = ["PLUS", "AH", "Jumbo", "Milner", "Beemster", "Old Amsterdam", "Leerdammer"]
    
    # Try to match known brands first
    for brand in known_brands:
        if name.startswith(brand):
            return brand
    
    # If no known brand found, take first word
    return name.split()[0] if name else ""

# Schema for product extraction
PRODUCT_SCHEMA = {
    "baseSelector": ".list-item.cart-item-wrapper.plp-item-wrapper",
    "fields": [
        {
            "name": "name",
            "selector": ".plp-item-name h3 span",
            "type": "text",
            "transform": lambda x: x.strip() if x else None
        },
        {
            "name": "image",
            "selector": ".plp-item-image img",
            "type": "attribute",
            "attribute": "src"
        },
        {
            "name": "_price_integer",
            "selector": ".product-header-price-integer span",
            "type": "text"
        },
        {
            "name": "_price_decimal",
            "selector": ".product-header-price-decimals span",
            "type": "text"
        },
        {
            "name": "price",
            "type": "computed",
            "compute": lambda item: parse_price(item.get('_price_integer', ''), item.get('_price_decimal', '')),
            "output": True,
            "required": True
        },
        {
            "name": "unit_info",
            "selector": ".plp-item-complementary .margin-bottom-xs span",
            "type": "text",
            "transform": lambda x: x.strip() if x else None
        },
        {
            "name": "unit_size",
            "selector": ".plp-item-complementary .margin-bottom-xs span",
            "type": "text",
            "transform": extract_unit_size
        },
        {
            "name": "brand",
            "selector": ".plp-item-name h3 span",
            "type": "text",
            "transform": extract_brand
        }
    ],
    "wait_for": ".list-item.cart-item-wrapper.plp-item-wrapper"
}

def calculate_price_per_unit(price: float, unit_size: str) -> tuple[float, str]:
    """Calculate price per unit (kg or piece) from price and unit size."""
    if not unit_size:
        return None, None
        
    # Convert unit size to lowercase for easier matching
    unit_size = unit_size.lower()
    
    # Handle pieces (stuks)
    stuk_match = re.search(r'(\d+)\s*stuk', unit_size)
    if stuk_match:
        pieces = int(stuk_match.group(1))
        if pieces > 0:
            return price / pieces, "stuk"
    
    # Handle weight in grams
    gram_match = re.search(r'per\s*(\d+(?:[.,]\d+)?)\s*g', unit_size)
    if gram_match:
        grams = float(gram_match.group(1).replace(',', '.'))
        if grams > 0:
            # Convert to price per kg
            return (price * 1000) / grams, "kilo"
    
    # Handle weight in kg
    kg_match = re.search(r'per\s*(\d+(?:[.,]\d+)?)\s*kg', unit_size)
    if kg_match:
        kgs = float(kg_match.group(1).replace(',', '.'))
        if kgs > 0:
            return price / kgs, "kilo"
            
    return None, None

async def scrape_plus_products(search_term: str) -> list:
    """Scrape products from Plus supermarket."""
    logger.info(f"Starting product search for '{search_term}'")
    
    # Check cache first
    cache_file = get_cache_file(search_term)
    if not should_update_cache(cache_file):
        cached_products = load_from_cache(search_term)
        if cached_products:
            return cached_products
    
    # Configure browser
    browser_config = BrowserConfig(
        headless=True,  # Set to true for better performance
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    try:
        # Initialize and run crawler
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # Construct search URL
            url = f"https://www.plus.nl/zoekresultaten?SearchTerm={search_term}"
            
            # Extract products using JSON CSS strategy
            strategy = JsonCssExtractionStrategy(PRODUCT_SCHEMA)
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    extraction_strategy=strategy,
                    cache_mode=CacheMode.BYPASS,
                    wait_for=".list-item.cart-item-wrapper.plp-item-wrapper",
                    js_code="""
                        async function handlePage() {
                            const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                            
                            // Handle cookie consent if present
                            try {
                                const cookieButton = document.querySelector('#accept-cookies');
                                if (cookieButton) {
                                    cookieButton.click();
                                    await delay(1000);
                                }
                            } catch (e) {
                                console.log('No cookie banner found');
                            }
                            
                            // Wait for products to load
                            let attempts = 0;
                            const maxAttempts = 20;
                            while (attempts < maxAttempts) {
                                const products = document.querySelectorAll('.list-item.cart-item-wrapper.plp-item-wrapper');
                                if (products.length > 0) {
                                    console.log(`Found ${products.length} products`);
                                    break;
                                }
                                await delay(500);
                                attempts++;
                                console.log(`Waiting for products... Attempt ${attempts}/${maxAttempts}`);
                            }
                            
                            // Scroll to load more products
                            window.scrollTo(0, document.documentElement.scrollHeight);
                            await delay(2000);
                            
                            return true;
                        }
                        
                        handlePage();
                    """
                )
            )
            
            if not result.extracted_content:
                logger.warning("No products extracted")
                return []
            
            products = json.loads(result.extracted_content)
            logger.debug(f"Extracted {len(products)} products from page")
            
            if not products:
                logger.warning("No products found in extracted content")
                return []
            
            # Clean and process products
            cleaned_products = []
            for idx, product in enumerate(products):
                logger.debug(f"\nProcessing product {idx + 1}:")
                logger.debug(f"Raw product data: {json.dumps(product, indent=2)}")
                
                # Clean the product data
                cleaned_product = {k: v for k, v in product.items() if not k.startswith('_')}
                
                # Parse price
                price_integer = product.get('_price_integer', '')
                price_decimal = product.get('_price_decimal', '')
                price = parse_price(price_integer, price_decimal)
                if price > 0:
                    cleaned_product['price'] = price
                    logger.debug(f"Added price: {price}")
                else:
                    logger.warning(f"Invalid price for product {idx + 1}: integer={price_integer}, decimal={price_decimal}")
                
                # Handle unit size and price per unit
                unit_size = cleaned_product.get('unit_size', '')
                if unit_size:
                    # Extract grams from unit size
                    grams = 0
                    if 'g' in unit_size:
                        match = re.search(r'(\d+)g', unit_size)
                        if match:
                            grams = float(match.group(1))
                    
                    if grams > 0:
                        price_per_unit_value, price_per_unit_unit = calculate_price_per_unit(price, unit_size)
                        cleaned_product['price_per_unit_value'] = price_per_unit_value
                        cleaned_product['price_per_unit_unit'] = price_per_unit_unit
                        cleaned_product['unit_price_display'] = f"€{price_per_unit_value:.2f} / {price_per_unit_unit}"
                
                # Extract product ID from image URL
                image_url = product.get('image', '')
                product_id = None
                
                if image_url:
                    # Try to extract ID from image URL (format: .../140299_M/...)
                    match = re.search(r'/(\d+)_M/', image_url)
                    if match:
                        product_id = match.group(1)
                        logger.debug(f"Extracted product ID from image URL: {product_id}")
                
                # Add link using product ID
                if product_id:
                    name = product.get('name', '').lower()
                    
                    # Convert name to URL-friendly format
                    url_name = name.lower()
                    url_name = re.sub(r'[^a-z0-9\s-]', '', url_name)  # Remove special chars
                    url_name = re.sub(r'\s+', '-', url_name.strip())  # Replace spaces with hyphens
                    url_name = re.sub(r'-+', '-', url_name)  # Remove multiple hyphens
                    
                    # Add product type (tray) for packaged cheese
                    if 'plakken' in name:
                        url_name = f"{url_name}-tray"
                    
                    # Construct the link
                    cleaned_product['link'] = f"https://www.plus.nl/product/{url_name}-{product_id}"
                    logger.debug(f"Constructed link from ID: {cleaned_product['link']}")
                else:
                    logger.warning(f"No product ID found for product: {product.get('name', 'Unknown')}")
                
                cleaned_product['store'] = 'plus'
                cleaned_product['scraped_at'] = datetime.now().isoformat()
                cleaned_products.append(cleaned_product)
                logger.debug(f"Final cleaned product: {json.dumps(cleaned_product, indent=2)}\n")
            
            # Save to cache
            save_to_cache(search_term, cleaned_products)
            
            return cleaned_products
            
    except Exception as e:
        logger.error(f"Error scraping Plus products: {str(e)}")
        return []

# Test the scraper
if __name__ == "__main__":
    import asyncio
    
    async def test_scraper():
        # Test with a specific search term
        products = await scrape_plus_products("kaas plakken")
        
        print("\n=== SCRAPING RESULTS ===")
        print(f"Found {len(products)} products")
        
        if products:
            print("\nFirst product details:")
            print(json.dumps(products[0], indent=2))
    
    # Run the test
    asyncio.run(test_scraper())
