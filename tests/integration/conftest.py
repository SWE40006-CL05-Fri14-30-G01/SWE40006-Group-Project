import pytest
import os 
import uuid
from sqlalchemy import create_engine, text

# App Address Setup 
INT_TEST_BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")

# Safety Check 
# Ensures that conftest file only runs if the test db is PostgreSQL 
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgres") or "test" not in DATABASE_URL:
    pytest.exit(
        "DATABASE_URL must be set to a PostgreSQL test db! The URL must contain 'test'!",
        returncode=2,
        )

# Task Label 
# Tasks created in integration tests have a title starting w/ this label 
INT_TEST_LABEL = "[integration-test]"

# Running App 
# Get where the running app is
@pytest.fixture(scope="session")
def int_test_base_url():
    return INT_TEST_BASE_URL

# Test Database 
# Provides connection to the test db
@pytest.fixture(scope="session")
def int_test_db():
    engine = create_engine(DATABASE_URL.replace("postgres://", "postgresql://", 1))
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar_one()
    if "test" not in db_name:
        pytest.exit(
            f"Connected to database '{db_name}', which is not a test database.",
            returncode=2,
        )
    yield engine
    engine.dispose()

# Remove Leftovers from Crashed Runs (only on test labels)
@pytest.fixture(scope="session", autouse=True)
def int_test_remove_leftovers(int_test_db):
    with int_test_db.begin() as conn:
        conn.execute(
            text("DELETE FROM tasks WHERE title LIKE :p"), {"p": f"{INT_TEST_LABEL}%"}
        )

# Test Task Title
# Unique task title which will applied to tasks created during tests
# Tasks with this title will be deleted after the test 
@pytest.fixture
def int_test_title(int_test_db):
    title = f"{INT_TEST_LABEL} {uuid.uuid4().hex[:8]}" # Builds unique title
    yield title 
    with int_test_db.begin() as conn:
        conn.execute(text("DELETE FROM tasks WHERE title = :t"), {"t": title}) # Clean up

