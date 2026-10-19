""" Integration Tests for Task Creation (via running app & PostgreSQL) """
import pytest
import requests
from sqlalchemy import text

pytestmark = pytest.mark.integration


def fetch_task(db, title):
    # Read the task's row from the test db - None if missing
    with db.connect() as conn:
        return conn.execute(
            text("SELECT title, assignee, status FROM tasks WHERE title = :t"),
            {"t": title},
        ).first()

def test_create_task(int_test_base_url, int_test_db, int_test_title):
    response = requests.post(
        f"{int_test_base_url}/add",
        data={"title": int_test_title, "assignee": "Integration Tester"},
        timeout=10,
    )
    assert response.status_code == 200

    row = fetch_task(int_test_db, int_test_title)
    assert row is not None
    assert row.assignee == "Integration Tester"
    assert row.status == "To Do" # New tasks start in To Do

def test_reject_empty_title(int_test_base_url, int_test_db, int_test_title):
    # Unique value goes in "assignee" so that can prove that no row was created
    response = requests.post(
        f"{int_test_base_url}/add",
        data={"title": "   ", "assignee": int_test_title},
        timeout=10,
    )
    assert "Task title cannot be empty." in response.text

    with int_test_db.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM tasks WHERE assignee = :a"),
            {"a": int_test_title},
        ).scalar_one()
    assert count == 0