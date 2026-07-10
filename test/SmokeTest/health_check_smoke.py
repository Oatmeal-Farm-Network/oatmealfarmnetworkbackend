import requests
import pytest

# Base URL for the backend (assuming it's running on localhost:8000)
BASE_URL = "http://localhost:8000"


def test_health_check_endpoint():
    """Smoke test for the health check endpoint.

    This test verifies that the backend is running and the health endpoint
    returns a successful response. It is intended to be fast and shallow
    for use in CI/CD pipelines.
    """
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        response.raise_for_status()  # Raises an HTTPError for bad responses
    except requests.exceptions.RequestException as e:
        pytest.fail(f"Health check endpoint failed: {e}")

    # Basic validation: status code 200 and JSON response
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict), "Health endpoint should return a JSON object"
    # Common pattern: check for a status field; adjust based on actual implementation
    assert data.get("status") in ["ok", "healthy", "success"], \
        f"Unexpected health status: {data.get('status')}"