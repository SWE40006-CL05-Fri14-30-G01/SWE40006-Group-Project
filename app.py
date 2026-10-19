"""DevOps Task Manager - a small Kanban board built with Flask and SQLAlchemy."""

import logging
import os
import time

from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("task_manager")

STATUSES = ["To Do", "In Progress", "Done"]
MAX_TITLE_LENGTH = 200
MAX_ASSIGNEE_LENGTH = 100

db = SQLAlchemy()


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(MAX_TITLE_LENGTH), nullable=False)
    assignee = db.Column(db.String(MAX_ASSIGNEE_LENGTH), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="To Do")

    def __repr__(self):
        return f"<Task {self.id} {self.title!r} [{self.status}]>"


def _database_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///tasks.db")
    # SQLAlchemy 1.4+ no longer accepts the legacy "postgres://" scheme.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=_database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        BUILD_ID=os.environ.get("BUILD_ID", "Local Dev"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    with app.app_context():
        # create_all only creates missing tables; existing data is never dropped.
        db.create_all()
        # Release pooled connections so forked gunicorn workers open their own.
        # (An in-memory SQLite DB lives on its one connection, so keep it.)
        if ":memory:" not in app.config["SQLALCHEMY_DATABASE_URI"]:
            db.engine.dispose()

    register_request_timing(app)
    register_routes(app)
    return app


def register_request_timing(app):
    @app.before_request
    def start_timer():
        g.request_start = time.perf_counter()

    @app.after_request
    def log_request_duration(response):
        start = g.pop("request_start", None)
        if start is not None:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %s in %.2f ms",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )
        return response


def register_routes(app):
    @app.context_processor
    def inject_build_id():
        return {"build_id": app.config["BUILD_ID"]}

    @app.get("/")
    def index():
        tasks = Task.query.order_by(Task.id).all()
        board = {status: [t for t in tasks if t.status == status] for status in STATUSES}
        return render_template("index.html", board=board, statuses=STATUSES)

    @app.post("/add")
    def add_task():
        title = request.form.get("title", "").strip()
        assignee = request.form.get("assignee", "").strip()

        errors = []
        if not title:
            errors.append("Task title cannot be empty.")
        elif len(title) > MAX_TITLE_LENGTH:
            errors.append(f"Task title must be {MAX_TITLE_LENGTH} characters or fewer.")
        if not assignee:
            errors.append("Assignee cannot be empty.")
        elif len(assignee) > MAX_ASSIGNEE_LENGTH:
            errors.append(f"Assignee must be {MAX_ASSIGNEE_LENGTH} characters or fewer.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("index"))

        try:
            db.session.add(Task(title=title, assignee=assignee))
            db.session.commit()
            flash(f'Task "{title}" created.', "success")
        except Exception:
            db.session.rollback()
            logger.exception("Failed to create task")
            flash("Could not create the task. Please try again.", "danger")
        return redirect(url_for("index"))

    @app.post("/update/<int:task_id>")
    def update_task(task_id):
        task = db.session.get(Task, task_id)
        if task is None:
            flash("Task not found.", "warning")
            return redirect(url_for("index"))

        new_status = request.form.get("status", "").strip()
        if new_status not in STATUSES:
            flash("Invalid status.", "danger")
            return redirect(url_for("index"))

        try:
            task.status = new_status
            db.session.commit()
            flash(f'Moved "{task.title}" to {new_status}.', "info")
        except Exception:
            db.session.rollback()
            logger.exception("Failed to update task %s", task_id)
            flash("Could not update the task. Please try again.", "danger")
        return redirect(url_for("index"))

    @app.post("/delete/<int:task_id>")
    def delete_task(task_id):
        task = db.session.get(Task, task_id)
        if task is None:
            flash("Task not found.", "warning")
            return redirect(url_for("index"))

        try:
            title = task.title
            db.session.delete(task)
            db.session.commit()
            flash(f'Deleted "{title}".', "secondary")
        except Exception:
            db.session.rollback()
            logger.exception("Failed to delete task %s", task_id)
            flash("Could not delete the task. Please try again.", "danger")
        return redirect(url_for("index"))

    @app.get("/health")
    def health():
        build_id = app.config["BUILD_ID"]
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            db.session.rollback()
            logger.exception("Health check could not reach the database")
            return jsonify(status="unhealthy", database="unreachable", build_id=build_id), 503
        return jsonify(status="healthy", database="ok", build_id=build_id), 200


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
