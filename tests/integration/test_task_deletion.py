""" Integration Tests for Task Deletion (via running app & PostgreSQL) """
import pytest
import requests
from sqlalchemy import text

pytestmark = pytest.mark.integration

def insert_task(db, title, status="To Do"):
    with db.begin() as conn:
        return conn.execute(
            text("INSERT INTO tasks (title, assignee, status) "
                 "VALUES (:t, 'Integration Test', :s) RETURNING id"),
            {"t": title, "s": status},
        ).scalar_one()

def test_delete_task(int_test_base_url, int_test_db, int_test_title):
    task_id = insert_task(int_test_db, int_test_title)

    response = requests.post(f"{int_test_base_url}/delete/{task_id}", timeout=10)
    assert response.status_code == 200

    with int_test_db.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM tasks WHERE id = :i"), {"i": task_id}
        ).scalar_one()
    assert count == 0

def test_handle_delete_missing_task(int_test_base_url):
    response = requests.post(f"{int_test_base_url}/delete/999999999", timeout=10)
    assert response.status_code == 200
    assert "Task not found." in response.text