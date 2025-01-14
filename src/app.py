from flask import Flask, render_template, request, jsonify, send_from_directory
from ah_scraper import scrape_ah_products
from jumbo_scraper import scrape_jumbo_products
from plus_scraper import scrape_plus_products
import json
import os
import asyncio
import nest_asyncio
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import hypercorn.asyncio
import hypercorn.config
import re
import logging
from watchfiles import run_process

# Enable nested async operations
nest_asyncio.apply()

app = Flask(__name__, static_folder='static')

# Initialize session storage
grocery_list = []
selected_products = {}

# Create thread pool executor
executor = ThreadPoolExecutor(max_workers=4)

# Helper functions for Jinja2 templates
def format_price(price):
    try:
        if isinstance(price, str):
            price = float(price.replace('€', '').replace(',', '.'))
        return "{:.2f}".format(price).replace('.', ',')
    except (ValueError, TypeError):
        return "0,00"

def format_unit_size(unit_size):
    """Format unit size for display"""
    if not unit_size:
        return ''
    
    unit_size = str(unit_size).lower().strip()
    
    # Handle piece-based items (stuks)
    if 'stuk' in unit_size:
        match = re.search(r'(\d+)\s*stuk', unit_size)
        if match:
            return f"{match.group(1)} stuks"
        return unit_size
    
    # Handle "Per X" format
    per_match = re.search(r'per\s+(\d+(?:[.,]\d+)?)\s*([gk]|kg|gram)', unit_size)
    if per_match:
        num = per_match.group(1).replace(',', '.')
        unit = per_match.group(2).lower()
        if unit in ['k', 'kg']:
            return f"Per {num} kg"
        return f"Per {num} g"
    
    # Handle kilogram units
    if any(x in unit_size for x in ['kg', 'kilo']):
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*k(?:ilo|g)', unit_size)
        if match:
            return f"{match.group(1)} kg"
    
    # Handle gram units
    gram_match = re.search(r'(\d+(?:[.,]\d+)?)\s*g(?:ram)?', unit_size)
    if gram_match:
        grams = float(gram_match.group(1))
        if grams >= 1000:
            return f"{grams/1000:.1f} kg"
        return f"{int(grams)} g"
    
    # Try to extract just the number for products like "410g" without space
    numeric_match = re.search(r'^(\d+)$', unit_size)
    if numeric_match:
        value = float(numeric_match.group(1))
        if value >= 1000:
            return f"{value/1000:.1f} kg"
        return f"{int(value)} g"
    
    return unit_size

def format_price_per_unit(price, unit_size):
    """Format price per unit for display"""
    if not price or not unit_size:
        return ''
    
    try:
        # Parse price consistently
        if isinstance(price, str):
            price = float(price.replace('€', '').replace(',', '.'))
        
        unit_size = str(unit_size).lower().strip()
        
        # Handle piece-based items (stuks)
        if 'stuk' in unit_size:
            match = re.search(r'(\d+)\s*stuk', unit_size)
            if match:
                pieces = int(match.group(1))
                if pieces > 0:
                    price_per_piece = price / pieces
                    return f"€{format_price(price_per_piece)}/stuk"
            return f"€{format_price(price)}/stuk"
        
        # Handle slices (plakken)
        if 'plak' in unit_size:
            match = re.search(r'(\d+)\s*plak', unit_size)
            if match:
                slices = int(match.group(1))
                if slices > 0:
                    price_per_slice = price / slices
                    return f"€{format_price(price_per_slice)}/plak"
            return f"€{format_price(price)}/plak"
        
        # For weight-based items
        grams = 0
        
        # First try to get weight from "Per X g/kg" format
        per_match = re.search(r'per\s+(\d+(?:[.,]\d+)?)\s*([gk]|kg|gram)', unit_size)
        if per_match:
            num = per_match.group(1).replace(',', '.')
            unit = per_match.group(2).lower()
            if unit in ['k', 'kg']:
                grams = float(num) * 1000
            else:
                grams = float(num)
        else:
            # Handle kg/kilo
            if any(x in unit_size for x in ['kg', 'kilo']):
                match = re.search(r'(\d+(?:[.,]\d+)?)\s*k(?:ilo|g)', unit_size)
                if match:
                    kg = float(match.group(1).replace(',', '.'))
                    grams = kg * 1000
                    
            # Handle grams
            elif any(x in unit_size for x in ['g', 'gram']):
                match = re.search(r'(\d+(?:[.,]\d+)?)\s*g(?:ram)?', unit_size)
                if match:
                    grams = float(match.group(1).replace(',', '.'))
                    
            # Handle numeric-only values (assume grams)
            else:
                numeric_match = re.search(r'^(\d+)$', unit_size)
                if numeric_match:
                    grams = float(numeric_match.group(1))
        
        # Calculate and format price per kg
        if grams > 0:
            price_per_kg = (price / grams) * 1000
            return f"€{format_price(price_per_kg)}/kg"
        
        return f"€{format_price(price)}"
        
    except Exception as e:
        print(f"Error formatting price per unit: {str(e)}")
        return f"€{format_price(price)}"

# Register template functions
app.jinja_env.filters['formatPrice'] = format_price
app.jinja_env.filters['formatUnitSize'] = format_unit_size
app.jinja_env.filters['formatPricePerUnit'] = format_price_per_unit

# Helper function to run sync function in executor
def run_in_executor(func, *args):
    return executor.submit(func, *args).result()

@app.route('/')
def index():
    return render_template('index.html', grocery_list=grocery_list, selected_products=selected_products)

@app.route('/add_item', methods=['POST'])
def add_item():
    item = request.form.get('item')
    if item and item not in grocery_list:
        grocery_list.append(item)
    return jsonify({'success': True, 'grocery_list': grocery_list})

@app.route('/remove_item', methods=['POST'])
def remove_item():
    item = request.form.get('item')
    if item in grocery_list:
        grocery_list.remove(item)
        if item in selected_products:
            del selected_products[item]
    return jsonify({'success': True, 'grocery_list': grocery_list})

@app.route('/clear_list', methods=['POST'])
def clear_list():
    grocery_list.clear()
    selected_products.clear()
    return jsonify({'success': True})

async def search_both_stores(item):
    """Run both scrapers concurrently"""
    # Create tasks for both scrapers
    ah_task = run_sync_in_executor(scrape_ah_products, item)
    jumbo_task = scrape_jumbo_products(item)
    
    # Run both tasks concurrently
    ah_products, jumbo_products = await asyncio.gather(
        ah_task, jumbo_task,
        return_exceptions=True  # This will prevent one failure from affecting the other
    )
    
    products = []
    
    # Handle AH results
    if isinstance(ah_products, Exception):
        print(f"Error searching AH products: {str(ah_products)}")
    elif ah_products:
        print(f"Found {len(ah_products)} AH products")
        products.extend(ah_products)
    
    # Handle Jumbo results
    if isinstance(jumbo_products, Exception):
        print(f"Error searching Jumbo products: {str(jumbo_products)}")
    elif jumbo_products:
        print(f"Found {len(jumbo_products)} Jumbo products")
        products.extend(jumbo_products)
    
    return products

def calculate_price_per_unit(product):
    """Calculate price per unit (kg or piece) for sorting"""
    try:
        # If product has price_per_unit_value from scraper, use it directly
        if product.get('price_per_unit_value') is not None:
            return float(product['price_per_unit_value'])
        
        # Get base price
        price = float(str(product['price']).replace('€', '').replace(',', '.'))
        unit_size = str(product.get('unit_size', '')).lower().strip()
        
        # For piece-based items (stuks)
        if 'stuk' in unit_size:
            match = re.search(r'(\d+)\s*stuk', unit_size)
            if match:
                pieces = int(match.group(1))
                return price / pieces if pieces > 0 else price
            return price
        
        # For slice-based items (plakken)
        if 'plak' in unit_size:
            match = re.search(r'(\d+)\s*plak', unit_size)
            if match:
                slices = int(match.group(1))
                return price / slices if slices > 0 else price
            return price
        
        # For weight-based items
        grams = 0
        
        # Handle kg/kilo
        if 'kg' in unit_size or 'kilo' in unit_size:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*k(?:ilo|g)', unit_size)
            if match:
                grams = float(match.group(1).replace(',', '.')) * 1000
        
        # Handle grams
        elif 'g' in unit_size or 'gram' in unit_size:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*g(?:ram)?', unit_size)
            if match:
                grams = float(match.group(1).replace(',', '.'))
        
        # Handle numeric-only values (assume grams)
        elif unit_size.replace(' ', '').isdigit():
            grams = float(unit_size)
        
        if grams > 0:
            return (price / grams) * 1000  # Convert to price per kg
        
        return price
            
    except (ValueError, TypeError, ZeroDivisionError) as e:
        print(f"Error calculating price per unit: {e}")
        return float('inf')  # Return infinity for invalid calculations

@app.route('/search_products', methods=['POST'])
async def search_products():
    """Search for products in selected stores"""
    try:
        data = request.get_json()
        search_term = data.get('search_term')
        selected_stores = data.get('stores', [])
        sort_by = data.get('sort_by', 'price_per_unit')  # Changed default to price_per_unit
        
        # Get products from all selected stores
        tasks = []
        if 'ah' in selected_stores:
            tasks.append(scrape_ah_products(search_term))
        if 'jumbo' in selected_stores:
            tasks.append(scrape_jumbo_products(search_term))
        if 'plus' in selected_stores:
            tasks.append(scrape_plus_products(search_term))
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine and process results
        products = []
        seen_products = set()  # Track unique products by store and name
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Error searching products: {str(result)}")
                continue
            elif isinstance(result, list):
                for product in result:
                    if not isinstance(product, dict):
                        continue
                    # Create a unique key for each product based on store and name
                    product_key = f"{product.get('store')}_{product.get('name')}"
                    if product_key not in seen_products:
                        seen_products.add(product_key)
                        products.append(product)
            elif result and isinstance(result, dict):
                product_key = f"{result.get('store')}_{result.get('name')}"
                if product_key not in seen_products:
                    seen_products.add(product_key)
                    products.append(result)
        
        # Calculate price per unit for all products
        for product in products:
            try:
                # First try to use price_per_unit_value if available
                if product.get('price_per_unit_value') is not None:
                    product['price_per_unit'] = float(product['price_per_unit_value'])
                else:
                    product['price_per_unit'] = calculate_price_per_unit(product)
            except Exception as e:
                print(f"Error calculating price per unit: {str(e)}")
                product['price_per_unit'] = float('inf')
        
        # Sort products based on sort_by parameter
        if sort_by == 'price_per_unit':
            products.sort(key=lambda x: x.get('price_per_unit', float('inf')))
        elif sort_by == 'price':
            products.sort(key=lambda x: float(str(x.get('price', '0')).replace('€', '').replace(',', '.')))
        
        if not products:
            return jsonify({
                'products': [],
                'count': 0,
                'message': 'No products found. Please try a different search term.'
            })
            
        return jsonify({
            'products': products,
            'count': len(products)
        })
        
    except Exception as e:
        print(f"Error in search_products: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/select_product', methods=['POST'])
def select_product():
    data = request.json
    item = data.get('item')
    product = data.get('product')
    compared_with = data.get('compared_with')  # New field for comparison product
    
    if item and product:
        if compared_with:
            # Store both the selected product and its comparison
            product['comparedWith'] = compared_with
        selected_products[item] = product
        return jsonify({
            'success': True, 
            'selected_products': selected_products,
            'grocery_list': grocery_list
        })
    return jsonify({'success': False, 'error': 'Invalid data'})

@app.route('/delete_product', methods=['POST'])
def delete_product():
    data = request.json
    item = data.get('item')
    
    if item and item in selected_products:
        del selected_products[item]
        return jsonify({'success': True, 'selected_products': selected_products})
    return jsonify({'success': False, 'error': 'Product not found'})

@app.template_filter('regex_replace')
def regex_replace(s, find, replace):
    """Perform a regex substitution on a string."""
    return re.sub(find, replace, str(s))

if __name__ == '__main__':
    # Enable debug mode in Flask
    app.debug = True
    
    # Create Hypercorn config
    config = hypercorn.config.Config()
    config.bind = ["127.0.0.1:5000"]
    config.use_reloader = True
    config.reload_dirs = ["src"]
    
    # Run with Hypercorn
    asyncio.run(hypercorn.asyncio.serve(app, config)) 