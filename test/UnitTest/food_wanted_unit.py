"""
Unit tests for food_wanted module.
"""
import pytest
from unittest.mock import MagicMock

def test_food_wanted_router_exists():
    """Test that the food_wanted router is properly defined."""
    # Mock the database engine to prevent connection attempts during import
    from unittest.mock import patch
    with patch('app.database.engine') as mock_engine:
        # Create a mock connection that acts as a context manager
        mock_connection = MagicMock()
        # Make the context manager work correctly
        mock_engine.begin.return_value.__enter__.return_value = mock_connection
        mock_engine.begin.return_value.__exit__.return_value = None
        
        # Now import the module - this should not trigger a real DB connection
        from app.routers.food_wanted import food_wanted_router
        
        # Basic assertions
        assert food_wanted_router is not None
        assert hasattr(food_wanted_router, 'routes')
        # If we got here without exception, the import succeeded
        assert True
