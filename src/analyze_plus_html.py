import re
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import os

def get_page_html(url: str) -> str:
    """Fetch the page HTML using Selenium."""
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        driver.get(url)
        # Wait for product cards to be present
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.list-item.cart-item-wrapper.plp-item-wrapper'))
        )
        # Additional wait for dynamic content
        time.sleep(3)
        return driver.page_source
    except Exception as e:
        print(f"Error while fetching page: {str(e)}")
        raise
    finally:
        driver.quit()

def extract_product_sections(html_file: str, output_file: str, url: str = None):
    """Extract and save the complete HTML for each product section."""
    if url:
        # Fetch and save the HTML first
        html = get_page_html(url)
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Saved initial HTML to {html_file}")
    else:
        # Read existing HTML file
        with open(html_file, 'r', encoding='utf-8') as f:
            html = f.read()
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all product items
    products = soup.select('.list-item.cart-item-wrapper.plp-item-wrapper')
    
    # Extract complete product sections
    output = []
    for i, product in enumerate(products, 1):
        # Get product name for the header
        name = product.select_one('.plp-item-name h3 span')
        name_text = name.text if name else "Unknown"
        
        output.append(f"\n{'='*80}\nProduct {i}: {name_text}\n{'='*80}\n")
        # Add the complete HTML for this product
        output.append(product.prettify())
        
    # Save to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))

if __name__ == '__main__':
    url = "https://www.plus.nl/zoekresultaten?SearchTerm=kaas"
    input_file = 'output/plus_kaas_initial.html'
    output_file = 'output/plus_kaas_products.html'  # Changed filename to reflect full product content
    
    # Create output directory if it doesn't exist
    Path('output').mkdir(exist_ok=True)
    
    try:
        extract_product_sections(input_file, output_file, url=url)
        print(f"Extracted product sections saved to {output_file}")
        # Delete the initial HTML file after successful extraction
        if os.path.exists(input_file):
            os.remove(input_file)
            print(f"Deleted initial HTML file: {input_file}")
    except Exception as e:
        print(f"Error: {str(e)}") 