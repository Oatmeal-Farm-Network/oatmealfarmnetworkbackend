import pytest
from app.routers.precision_ag import router

def test_precision_ag_router_exists():
    """Test that the precision_ag router is properly defined."""
    assert router is not None
    assert hasattr(router, 'routes')
