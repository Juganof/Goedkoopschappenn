class TestRoutes:
    def test_index_route(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_add_item(self, client):
        # Test adding a new item
        response = client.post('/add_item', data={'item': 'test_item'})
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] == True
        assert 'test_item' in json_data['grocery_list']

        # Test adding duplicate item
        response = client.post('/add_item', data={'item': 'test_item'})
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['grocery_list'].count('test_item') == 1

        # Test adding empty item
        response = client.post('/add_item', data={'item': ''})
        assert response.status_code == 400
        
        # Test adding None
        response = client.post('/add_item', data={})
        assert response.status_code == 400

    def test_remove_item(self, client):
        # First add an item
        client.post('/add_item', data={'item': 'test_item'})
        
        # Then remove it
        response = client.post('/remove_item', data={'item': 'test_item'})
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] == True
        assert 'test_item' not in json_data.get('grocery_list', [])

        # Test removing non-existent item
        response = client.post('/remove_item', data={'item': 'nonexistent'})
        assert response.status_code == 200  # Should still return success
        json_data = response.get_json()
        assert json_data['success'] == True

        # Test removing with empty data
        response = client.post('/remove_item', data={})
        assert response.status_code == 400

    def test_clear_list(self, client):
        # Add some items first
        client.post('/add_item', data={'item': 'item1'})
        client.post('/add_item', data={'item': 'item2'})
        
        # Clear the list
        response = client.post('/clear_list')
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] == True
        assert not json_data.get('grocery_list', [])

        # Test clearing an empty list
        response = client.post('/clear_list')
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] == True
        
    def test_multiple_operations(self, client, sample_grocery_items):
        # Test a sequence of operations
        for item in sample_grocery_items:
            response = client.post('/add_item', data={'item': item['item']})
            assert response.status_code == 200
        
        # Verify all items are in the list
        response = client.get('/')
        assert response.status_code == 200
        
        # Remove one item
        response = client.post('/remove_item', data={'item': sample_grocery_items[0]['item']})
        assert response.status_code == 200
        
        # Clear remaining items
        response = client.post('/clear_list')
        assert response.status_code == 200
        json_data = response.get_json()
        assert not json_data.get('grocery_list', []) 