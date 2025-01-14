import pytest
from src.app import app as flask_app

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def sample_grocery_items():
    """Fixture providing sample grocery items for testing"""
    return [
        {"item": "milk", "quantity": 1},
        {"item": "bread", "quantity": 2},
        {"item": "eggs", "quantity": 12}
    ]

@pytest.fixture
def sample_product():
    """Fixture providing a sample product for testing"""
    return {
        "name": "Test Product",
        "price": "€2.99",
        "unit_size": "500g",
        "store": "Test Store",
        "url": "http://example.com/product"
    } 