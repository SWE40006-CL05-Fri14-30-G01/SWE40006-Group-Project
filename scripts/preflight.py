"""Fail closed until settings and Person 4's acceptance suites exist."""
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


def check():
    required = ["DOCKERHUB_IMAGE", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN",
                "DOCKERHUB_PULL_TOKEN", "TEST_DATABASE_URL", "TEST_SECRET_KEY",
                "PROD_DATABASE_URL", "PROD_SECRET_KEY"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing configuration: " + ", ".join(missing))
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9._-]*", os.environ["DOCKERHUB_IMAGE"]):
        raise ValueError("DOCKERHUB_IMAGE must be namespace/repository without a tag")
    test = urlsplit(os.environ["TEST_DATABASE_URL"])
    prod = urlsplit(os.environ["PROD_DATABASE_URL"])
    for connection in (test, prod):
        if connection.scheme not in ("postgresql", "postgresql+psycopg2") or not all(
                [connection.hostname, connection.username, connection.password, connection.path.strip("/")]):
            raise ValueError("Database URLs must provide PostgreSQL host, database and credentials")
    if test.path == prod.path or test.username == prod.username:
        raise ValueError("Use distinct test/production database names and users")
    for suite in ["tests/integration", "tests/e2e"]:
        if not list(Path(suite).rglob("test_*.py")):
            raise ValueError("Required acceptance suite is missing: " + suite)
    if not Path("requirements-e2e.txt").is_file():
        raise ValueError("Person 4 must supply requirements-e2e.txt")


if __name__ == "__main__":
    check()
    print("Release prerequisites present.")
