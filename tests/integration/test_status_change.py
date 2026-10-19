""" Integration Test for Status Change (via running app & PostgreSQL) """
import pytest
import requests 
from sqlalchemy import text 

pytestmark = pytest.mark.integration

def insert_task(db, title, status="To Do"):
    """ Insert a task into the test db + returns its id """
    with db.begin() as conn:
        return conn.execute(
            text("INSERT INTO tasks (title, assignee, status) "
                 "VALUES (:t, 'Integration Test', :s) RETURNING id"),
            {"t": title, "s": status},
        ).scalar_one()

def get_status(db, task_id):
    """ Read the task's status from the test db """
    with db.connect() as conn:
        return conn.execute(
            text("SELECT status FROM tasks WHERE id = :i"), {"i": task_id}
        ).scalar_one()

def test_change_status(int_test_base_url, int_test_db, int_test_title):
    task_id = insert_task(int_test_db, int_test_title)

    # Change status through the app's running route 
    response = requests.post(
        f"{int_test_base_url}/update/{task_id}",
        data={"status": "In Progress"},
        timeout=10,
    )
    assert response.status_code == 200 

    # Check the row in PostgreSQL 
    assert get_status(int_test_db, task_id) == "In Progress"

def reject_invalid_test_status(int_test_base_url, int_test_db, int_test_title):
    task_id = insert_task(int_test_db, int_test_title)

    response = requests.post(
        f"{int_test_base_url}/update/{task_id}",
        data={"status": "Archived"},
        timeout=10,
    )

    assert "Invalid status" in response.text
    assert get_status(int_test_db, task_id) == "To Do"