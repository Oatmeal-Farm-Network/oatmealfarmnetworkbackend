import pytest
from types import SimpleNamespace

from app.routers.dashboard import dashboard_summary, router


EXPECTED_ZERO_RESPONSE = {
    "fields": 0,
    "animals": 0,
    "pending_orders": 0,
    "upcoming_events": 0,
    "blog_posts": 0,
    "products": 0,
    "services": 0,
    "produce": 0,
    "aggregator_b2b_open": 0,
    "aggregator_farms": 0,
}


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self, row=None, should_raise=False):
        self.row = row
        self.should_raise = should_raise
        self.executed_query = None
        self.executed_params = None

    def execute(self, query, params):
        if self.should_raise:
            raise Exception("database error")

        self.executed_query = str(query)
        self.executed_params = params
        return FakeResult(self.row)


@pytest.mark.unit
def test_dashboard_router_exists():
    assert router is not None
    assert router.prefix == "/api/dashboard"


@pytest.mark.unit
def test_dashboard_router_has_summary_routes():
    route_paths = [route.path for route in router.routes]

    assert "/api/dashboard/summary" in route_paths
    assert "/api/dashboard/biz-summary" in route_paths


@pytest.mark.unit
def test_dashboard_summary_returns_counts_from_database():
    row = SimpleNamespace(
        fields=3,
        animals=7,
        pending_orders=2,
        upcoming_events=5,
        blog_posts=4,
        products=10,
        services=6,
        produce=8,
        aggregator_b2b_open=1,
        aggregator_farms=9,
    )
    db = FakeDB(row=row)

    response = dashboard_summary(business_id=101, db=db)

    assert response == {
        "fields": 3,
        "animals": 7,
        "pending_orders": 2,
        "upcoming_events": 5,
        "blog_posts": 4,
        "products": 10,
        "services": 6,
        "produce": 8,
        "aggregator_b2b_open": 1,
        "aggregator_farms": 9,
    }


@pytest.mark.unit
def test_dashboard_summary_passes_business_id_to_query_params():
    row = SimpleNamespace(
        fields=1,
        animals=1,
        pending_orders=1,
        upcoming_events=1,
        blog_posts=1,
        products=1,
        services=1,
        produce=1,
        aggregator_b2b_open=1,
        aggregator_farms=1,
    )
    db = FakeDB(row=row)

    dashboard_summary(business_id=555, db=db)

    assert db.executed_params == {"b": 555}


@pytest.mark.unit
def test_dashboard_summary_query_contains_expected_tables():
    row = SimpleNamespace(
        fields=1,
        animals=1,
        pending_orders=1,
        upcoming_events=1,
        blog_posts=1,
        products=1,
        services=1,
        produce=1,
        aggregator_b2b_open=1,
        aggregator_farms=1,
    )
    db = FakeDB(row=row)

    dashboard_summary(business_id=1, db=db)

    assert "Field" in db.executed_query
    assert "Animals" in db.executed_query
    assert "MarketplaceOrderItems" in db.executed_query
    assert "OFNEvents" in db.executed_query
    assert "blog" in db.executed_query
    assert "SFProducts" in db.executed_query
    assert "Services" in db.executed_query
    assert "Produce" in db.executed_query


@pytest.mark.unit
def test_dashboard_summary_returns_zero_response_when_no_row():
    db = FakeDB(row=None)

    response = dashboard_summary(business_id=101, db=db)

    assert response == EXPECTED_ZERO_RESPONSE


@pytest.mark.unit
def test_dashboard_summary_returns_zero_response_when_database_error():
    db = FakeDB(should_raise=True)

    response = dashboard_summary(business_id=101, db=db)

    assert response == EXPECTED_ZERO_RESPONSE


@pytest.mark.unit
def test_dashboard_summary_converts_none_values_to_zero():
    row = SimpleNamespace(
        fields=None,
        animals=None,
        pending_orders=None,
        upcoming_events=None,
        blog_posts=None,
        products=None,
        services=None,
        produce=None,
        aggregator_b2b_open=None,
        aggregator_farms=None,
    )
    db = FakeDB(row=row)

    response = dashboard_summary(business_id=101, db=db)

    assert response == EXPECTED_ZERO_RESPONSE
    
    
@pytest.mark.unit
def test_dashboard_summary_handles_zero_values_correctly():
    row = SimpleNamespace(
        fields=0,
        animals=0,
        pending_orders=0,
        upcoming_events=0,
        blog_posts=0,
        products=0,
        services=0,
        produce=0,
        aggregator_b2b_open=0,
        aggregator_farms=0,
    )

    db = FakeDB(row=row)

    response = dashboard_summary(business_id=101, db=db)

    assert response == EXPECTED_ZERO_RESPONSE
    

@pytest.mark.unit
def test_dashboard_summary_handles_mixed_none_and_values():
    row = SimpleNamespace(
        fields=2,
        animals=None,
        pending_orders=4,
        upcoming_events=None,
        blog_posts=1,
        products=None,
        services=3,
        produce=None,
        aggregator_b2b_open=5,
        aggregator_farms=None,
    )

    db = FakeDB(row=row)

    response = dashboard_summary(business_id=101, db=db)

    assert response == {
        "fields": 2,
        "animals": 0,
        "pending_orders": 4,
        "upcoming_events": 0,
        "blog_posts": 1,
        "products": 0,
        "services": 3,
        "produce": 0,
        "aggregator_b2b_open": 5,
        "aggregator_farms": 0,
    }
    

@pytest.mark.unit
def test_dashboard_summary_response_contains_expected_keys():
    db = FakeDB(row=None)

    response = dashboard_summary(business_id=101, db=db)

    expected_keys = {
        "fields",
        "animals",
        "pending_orders",
        "upcoming_events",
        "blog_posts",
        "products",
        "services",
        "produce",
        "aggregator_b2b_open",
        "aggregator_farms",
    }

    assert set(response.keys()) == expected_keys
    
