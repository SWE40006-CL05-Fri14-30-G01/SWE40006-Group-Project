""" Integration Test for Task Retrieval (via running app & PostgreSQL) """
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

def test_board_shows_db_task(int_test_base_url, int_test_db, int_test_title):
    insert_task(int_test_db, int_test_title)
    response = requests.get(f"{int_test_base_url}/", timeout=10)

    assert response.status_code == 200
    assert int_test_title in response.text