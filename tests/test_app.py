import os
import sys

# Point the module-level app at in-memory SQLite before it is imported.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402

from app import Task, create_app, db  # noqa: E402


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test",
        "BUILD_ID": "test-build",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def make_task(app, title="Write tests", assignee="Alice", status="To Do"):
    with app.app_context():
        task = Task(title=title, assignee=assignee, status=status)
        db.session.add(task)
        db.session.commit()
        return task.id


def test_index_renders_board_and_build_id(client):
    response = client.get("/")
    assert response.status_code == 200
    for column in (b"To Do", b"In Progress", b"Done"):
        assert column in response.data
    assert b"test-build" in response.data


def test_create_task(app, client):
    response = client.post(
        "/add", data={"title": "Set up CI", "assignee": "Bob"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Set up CI" in response.data
    with app.app_context():
        task = Task.query.one()
        assert task.title == "Set up CI"
        assert task.assignee == "Bob"
        assert task.status == "To Do"


def test_create_task_empty_title_fails(app, client):
    response = client.post(
        "/add", data={"title": "   ", "assignee": "Bob"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Task title cannot be empty." in response.data
    with app.app_context():
        assert Task.query.count() == 0


def test_create_task_empty_assignee_fails(app, client):
    response = client.post(
        "/add", data={"title": "Deploy", "assignee": ""}, follow_redirects=True
    )
    assert b"Assignee cannot be empty." in response.data
    with app.app_context():
        assert Task.query.count() == 0


def test_update_status(app, client):
    task_id = make_task(app)
    response = client.post(
        f"/update/{task_id}", data={"status": "In Progress"}, follow_redirects=True
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id).status == "In Progress"


def test_update_invalid_status_rejected(app, client):
    task_id = make_task(app)
    response = client.post(
        f"/update/{task_id}", data={"status": "Archived"}, follow_redirects=True
    )
    assert b"Invalid status." in response.data
    with app.app_context():
        assert db.session.get(Task, task_id).status == "To Do"


def test_update_missing_task(client):
    response = client.post("/update/999", data={"status": "Done"}, follow_redirects=True)
    assert b"Task not found." in response.data


def test_delete_task(app, client):
    task_id = make_task(app)
    response = client.post(f"/delete/{task_id}", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id) is None


def test_delete_missing_task(client):
    response = client.post("/delete/999", follow_redirects=True)
    assert b"Task not found." in response.data


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.is_json
    body = response.get_json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok"
    assert body["build_id"] == "test-build"


def test_health_reports_database_outage(client, monkeypatch):
    def unreachable(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(db.session, "execute", unreachable)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unhealthy"


def test_board_works_with_release_smoke_parser(app, client):
    """scripts/smoke.py reads the board HTML; template changes must not break it."""
    from scripts.smoke import find_task

    task_id = make_task(app, title="pipeline-smoke-contract")
    html = client.get("/").get_data(as_text=True)
    assert find_task(html, "pipeline-smoke-contract") == f"/delete/{task_id}"
    assert find_task(html, "not-on-the-board") is None


def test_board_exposes_selenium_hooks(app, client):
    task_id = make_task(app, title="Hooked", status="In Progress")
    html = client.get("/").get_data(as_text=True)
    assert f'data-testid="task-card" data-task-id="{task_id}" data-status="In Progress"' in html
    for hook in ("add-task-form", "task-title-input", "task-assignee-input",
                 "add-task-button", "move-task", "delete-task", "build-id"):
        assert f'data-testid="{hook}"' in html
