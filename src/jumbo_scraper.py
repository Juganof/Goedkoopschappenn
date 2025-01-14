import asyncio
import json
from pathlib import Path
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
import sys
import logging
import re
from datetime import datetime, timedelta
import random

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
    return CACHE_DIR / f"jumbo_{search_term.lower().replace(' ', '_')}_cache.json"

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

# Schema for product extraction
PRODUCT_SCHEMA = {
    "type": "array",
    "baseSelector": "article.product-container",
    "fields": [
        {
            "name": "name",
            "selector": ".title-link",
            "type": "text"
        },
        {
            "name": "image",
            "selector": ".product-image img",
            "type": "attribute",
            "attribute": "src"
        },
        {
            "name": "link",
            "selector": "a.link",
            "type": "attribute",
            "attribute": "href",
            "transform": "return value.startsWith('http') ? value : `https://www.jumbo.com${value}`;"
        },
        {
            "name": "price",
            "selector": ".current-price",
            "type": "text",
            "transform": "const match = value.match(/€\\s*(\\d+)[,\\.]?(\\d{0,2})/); if (!match) return ''; const euros = match[1]; const cents = match[2] || '00'; return `€${euros}.${cents.padEnd(2, '0')}`;"
        },
        {
            "name": "original_price",
            "selector": ".old-price",
            "type": "text",
            "transform": "const match = value?.match(/€\\s*(\\d+)[,\\.]?(\\d{0,2})/); if (!match) return null; const euros = match[1]; const cents = match[2] || '00'; return `€${euros}.${cents.padEnd(2, '0')}`;"
        },
        {
            "name": "is_sale",
            "selector": ".promotional-price, .bonus-price",
            "type": "exists"
        },
        {
            "name": "unit_size",
            "selector": ".title-link",
            "type": "text",
            "transform": "const match = value.match(/(\\d+)\\s*([gk]|kg|gram|plakken|stuk)(?:[^a-z]|$)/i); if (match) { const num = match[1]; const unit = match[2].toLowerCase(); if (unit === 'g' || unit === 'gram') return num + 'g'; if (unit === 'k' || unit === 'kg') return (num * 1000) + 'g'; if (unit === 'plakken') return num + ' plakken'; return num + ' stuk'; } else { const lowerValue = value.toLowerCase(); if (lowerValue.includes('half') || lowerValue.endsWith('-half') || lowerValue.endsWith(' half')) return '400g'; if (lowerValue.includes('heel') || lowerValue.endsWith('-heel') || lowerValue.endsWith(' heel')) return '800g'; return ''; }"
        },
        {
            "name": "debug_html",
            "selector": ".price-per-unit",
            "type": "html"
        },
        {
            "name": "price_per_unit_value",
            "selector": ".price-per-unit span[aria-hidden='true']:first-child",
            "type": "text",
            "transform": "return parseFloat(value.replace(',', '.'));"
        },
        {
            "name": "price_per_unit_unit",
            "selector": ".price-per-unit span[aria-hidden='true']:last-child",
            "type": "text",
            "transform": "return value.trim();"
        },
        {
            "name": "unit_price",
            "selector": ".price-per-unit .screenreader-only",
            "type": "text",
            "transform": "return value.replace('<!--[-->', '').replace('<!--]-->', '').trim();"
        },
        {
            "name": "properties",
            "selector": ".product-label",
            "type": "text",
            "multiple": True
        },
        {
            "name": "brand",
            "selector": ".product-brand",
            "type": "text"
        }
    ]
}

async def scrape_jumbo_products(search_term: str) -> list:
    """
    Scrape Jumbo products for a given search term, using cache when possible
    """
    logger.info(f"Starting product search for: {search_term}")
    
    # Check cache first
    cache_file = get_cache_file(search_term)
    if not should_update_cache(cache_file):
        cached_products = load_from_cache(search_term)
        if cached_products is not None:
            return cached_products
    
    logger.info(f"Cache needs update, scraping fresh data for: {search_term}")
    
    # Configure browser settings
    browser_config = BrowserConfig(
        headless=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    try:
        # Initialize and run crawler
        async with AsyncWebCrawler(config=browser_config) as crawler:
            url = f"https://www.jumbo.com/zoeken?searchType=keyword&searchTerms={search_term}"
            logger.info(f"Crawling URL: {url}")
            
            try:
                # Extract the products
                result = await crawler.arun(
                    url=url,
                    config=CrawlerRunConfig(
                        extraction_strategy=JsonCssExtractionStrategy(
                            PRODUCT_SCHEMA,
                            verbose=True
                        ),
                        cache_mode=CacheMode.BYPASS,
                        wait_for=".product-container",
                        js_code="""
                            async function handlePage() {
                                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                                
                                // Handle cookie consent if present
                                try {
                                    const cookieButton = document.querySelector('button[data-test="accept-cookies-button"]');
                                    if (cookieButton) {
                                        cookieButton.click();
                                        await delay(1000);
                                    }
                                } catch (e) {
                                    console.log('No cookie banner found');
                                }
                                
                                // Wait for products to load
                                let attempts = 0;
                                while (attempts < 10) {
                                    const products = document.querySelectorAll('article.product-container');
                                    if (products.length > 0) break;
                                    await delay(1000);
                                    attempts++;
                                }
                                
                                // Single scroll to load more products
                                window.scrollTo(0, document.documentElement.scrollHeight);
                                await delay(2000);
                                
                                return true;
                            }
                            
                            handlePage();
                        """
                    )
                )
                
                if result.extracted_content:
                    # Parse extracted content
                    raw_products = json.loads(result.extracted_content)
                    logger.info(f"Successfully extracted {len(raw_products)} products")
                    
                    # Process and format products
                    products = []
                    for product in raw_products:
                        try:
                            # Extract numeric price values
                            price_match = re.search(r'€\s*(\d+)[,\.]?(\d{0,2})', product['price'])
                            if not price_match:
                                continue
                            
                            price = float(f"{price_match.group(1)}.{price_match.group(2) or '00'}")
                            
                            # Parse unit price into value and unit
                            unit_price = product.get('unit_price', '')
                            price_per_unit_value = None
                            price_per_unit_unit = None
                            
                            if unit_price:
                                # Extract numeric value and unit from unit price string
                                # e.g. "€ 2,19 per stuk" -> (2.19, "stuk")
                                unit_price_match = re.search(r'€\s*(\d+)[,\.]?(\d{0,2})\s+per\s+(\w+)', unit_price)
                                if unit_price_match:
                                    price_per_unit_value = float(f"{unit_price_match.group(1)}.{unit_price_match.group(2) or '00'}")
                                    price_per_unit_unit = unit_price_match.group(3)
                            
                            # Extract unit size from product data
                            unit_size = product.get('unit_size', '')
                            if not unit_size:
                                unit_size = extract_unit_size(product['name'])
                            if not unit_size and price_per_unit_unit:
                                # If we have a per-unit price but no unit size, try to infer a standard size
                                if price_per_unit_unit == 'stuk':
                                    unit_size = '1 stuk'
                                elif price_per_unit_unit == 'kilo':
                                    # Assume standard bread size if not specified
                                    unit_size = '800g'
                            
                            # Format the product data
                            formatted_product = {
                                'name': product['name'],
                                'image': product['image'],
                                'link': product['link'] if product['link'].startswith('http') else f"https://www.jumbo.com{product['link']}",
                                'price': price,
                                'unit_size': unit_size,
                                'store': 'jumbo',
                                'scraped_at': datetime.now().isoformat(),
                                'unit_price': unit_price,
                                'price_per_unit_value': price_per_unit_value,
                                'price_per_unit_unit': price_per_unit_unit
                            }
                            
                            products.append(formatted_product)
                            
                        except Exception as e:
                            logger.error(f"Error processing product: {str(e)}")
                            continue
                    
                    # Sort products by price
                    products.sort(key=lambda x: x['price'])
                    
                    # After successful scraping, save to cache
                    if products:
                        save_to_cache(search_term, products)
                    
                    return products
                    
                else:
                    logger.error("No content was extracted")
                    return []
                    
            except Exception as e:
                logger.error(f"Error during crawling: {str(e)}")
                raise
                
    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        raise

def extract_unit_size(name: str) -> str:
    """Extract unit size from product name."""
    if not name:
        return ''
    
    # Common patterns for unit sizes
    patterns = [
        # Match piece counts first: "6 stuks", "6stuks", "10 Stuks"
        r'(\d+)\s*stuks?\b',
        # Match slice counts: "10 plakken", "10plakken"
        r'(\d+)\s*plakk?(?:en)?\b',
        # Match kilogram amounts: "1kg", "1 kg", "1 kilo", "1kilo"
        r'(\d+(?:[.,]\d+)?)\s*k(?:ilo|g)\b',
        # Match gram amounts: "400g", "400 g", "400 gram", "400gram"
        r'(\d+(?:[.,]\d+)?)\s*(?:g(?:ram)?)\b'
    ]
    
    name = name.lower()
    
    # First check bread-specific patterns
    if name.endswith('half'):
        return "400g"  # Standard weight for half bread
    elif any(word in name for word in [' heel', '-heel']):
        return "800g"  # Standard weight for whole bread
    elif 'half' in name:
        return "400g"  # Standard weight for half bread
    
    # Then try the generic patterns
    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            value = match.group(1)
            # Determine the unit based on the pattern
            if 'stuk' in pattern:
                return f"{value} stuks"
            elif 'plak' in pattern:
                return f"{value} plakken"
            elif 'k' in pattern and ('kg' in pattern or 'kilo' in pattern):
                # Convert kg to g for consistency
                value = float(value.replace(',', '.')) * 1000
                return f"{value}g"
            elif 'g' in pattern:
                return f"{value}g"
    
    return ''

if __name__ == "__main__":
    # Test the scraper
    async def test():
        search_term = sys.argv[1] if len(sys.argv) > 1 else "kaas"
        products = await scrape_jumbo_products(search_term)
        with open('jumbo_products.json', 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
    
    asyncio.run(test())
