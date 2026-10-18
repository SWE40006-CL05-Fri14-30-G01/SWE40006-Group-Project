import pytest
import os 
import sys

# Path Setup 
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Safety Check 
# Ensures that conftest file only runs if the test db is PostgreSQL 
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgres") or "test" not in DATABASE_URL:
    pytest.exit(
        "DATABASE_URL must be set to a PostgreSQL test db! The URL must contain 'test'!",
        returncode=2,
        )

from app import Task, db, create_app 

# Task Label 
# Tasks created in integration tests have a title starting w/ this label 
INT_TEST_LABEL = "[integration-test]"

# Clears tasks from db 
def clear_tasks_in_db(app):
    with app.app_context():
        db.session.remove()
        Task.query.filter(Task.title.startswith(INT_TEST_LABEL)).delete(
            synchronize_session=False
        )
        db.session.commit()

# Test App 
@pytest.fixture 
def int_test_app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "BUILD_ID": "integration-test-build",
    })
    clear_tasks_in_db(app) # Clears tasks in db BEFORE tests 
    yield app
    clear_tasks_in_db(app) # Clears tasks in db AFTER tests 

# Test Client 
@pytest.fixture 
def int_test_client(int_test_app):
    return int_test_app.test_client()
