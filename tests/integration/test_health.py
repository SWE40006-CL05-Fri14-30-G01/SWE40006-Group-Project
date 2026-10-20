""" Integration Test for the health endpoint (via running app) """
import os
import pytest
import requests

pytestmark = pytest.mark.integration

def test_check_health(int_test_base_url):
    response = requests.get(f"{int_test_base_url}/health", timeout=10)
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "healthy"

    expected_build_id = os.environ.get("EXPECTED_BUILD_ID")  # Set by pipeline
    if expected_build_id:
        assert body["build_id"] == expected_build_id