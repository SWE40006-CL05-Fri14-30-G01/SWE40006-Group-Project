""" Integration Test for Status Change (via running app & PostgreSQL) """

import pytest
import requests 
from sqlalchemy import text 

def insert_task(db,title, status="To Do")

@pytest.mark.integration 
def test_change_status(int_test_app, int_test_client):
    # Create task directly into the test database 
    with int_test_app.app_context():
        int_test_task = Task(title="[integration-test] Integration Test Task", assignee="Integration Test Assignee")
        db.session.add(int_test_task)
        db.session.commit()

        # Get Test Task's ID 
        int_test_task_id = int_test_task.id 

    # Change Status via App's route 
    int_test_response = int_test_client.post(
        f"/update/{int_test_task_id}",
        data={"status": "In Progress"},
        follow_redirects=True,
    )
    assert int_test_response.status_code == 200

    # Check status changed by checking value from row from PostgreSQL
    with int_test_app.app_context():
        updated_int_test = db.session.get(Task, int_test_task_id)
        assert updated_int_test.status == "In Progress"