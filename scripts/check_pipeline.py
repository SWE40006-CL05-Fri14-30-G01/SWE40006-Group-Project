"""Disposable real-Docker commissioning test; never contacts AWS or Docker Hub pushes.

Requires Docker/Compose, Python 3.10+, and free ports 15000, 15432, 18080.
Public base images are pulled; application images are pushed only to localhost.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.request import urlopen

from scripts.deploy import activate, release
from scripts.smoke import request, smoke, wait_ready


def run(*args, **kwargs):
    return subprocess.check_output(list(args), text=True, **kwargs).strip()


def main():
    # Fixed names deliberately fail on collisions rather than replacing existing data.
    registry = "taskmanager-check-registry"
    database = "taskmanager-check-db"
    project = "taskmanager-pipeline-check"
    output = Path("reports/container-check")
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, DATABASE_URL="postgresql://check:local-check-only@host.docker.internal:15432/check",
               SECRET_KEY="local-check-only", APP_PORT="18080")
    created = []
    active_env = None
    with tempfile.TemporaryDirectory(prefix="taskmanager-check-") as temporary:
        state = Path(temporary) / "state"
        try:
            run("docker", "run", "-d", "--name", registry, "-p", "127.0.0.1:15000:5000", "registry:2")
            created.append(registry)
            run("docker", "run", "-d", "--name", database, "-p", "15432:5432",
                "-e", "POSTGRES_USER=check", "-e", "POSTGRES_PASSWORD=local-check-only",
                "-e", "POSTGRES_DB=check", "postgres:15-alpine")
            created.append(database)
            for attempt in range(60):
                if subprocess.run(["docker", "exec", database, "pg_isready", "-U", "check"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Disposable PostgreSQL did not start")
            tag = "localhost:15000/taskmanager-check:good"
            run("docker", "build", "-t", tag, ".")
            run("docker", "push", tag)
            image = json.loads(run("docker", "image", "inspect", tag))[0]["RepoDigests"][0]
            good = {"image": image, "build_id": "check-good"}
            active_env = dict(env, IMAGE_REF=image, BUILD_ID="check-good")

            def start(item):
                activate(item, project, env)

            def verify(item):
                wait_ready("http://127.0.0.1:18080", item["build_id"], seconds=15)
                smoke("http://127.0.0.1:18080", item["build_id"])

            assert release(good, state, start, verify) == 0
            assert "pipeline-smoke-" not in urlopen("http://127.0.0.1:18080/").read().decode()
            request("http://127.0.0.1:18080", "/add", {"title": "Keep this task across rollback", "assignee": "container-check"})
            shutil.copy(state / "report.json", output / "success.json")
            # A genuinely broken image starts a process that immediately exits.
            bad_dockerfile = Path(temporary) / "Dockerfile.broken"
            bad_dockerfile.write_text('FROM ' + tag + '\nCMD ["python", "-c", "raise SystemExit(1)"]\n')
            bad_tag = "localhost:15000/taskmanager-check:broken"
            run("docker", "build", "-f", str(bad_dockerfile), "-t", bad_tag, ".")
            run("docker", "push", bad_tag)
            bad_image = json.loads(run("docker", "image", "inspect", bad_tag))[0]["RepoDigests"][0]
            bad = {"image": bad_image, "build_id": "check-broken"}
            assert release(bad, state, start, verify) == 1
            assert json.loads((state / "report.json").read_text())["status"] == "rolled-back-release-failed"
            assert json.loads((state / "current.json").read_text()) == good
            verify(good)
            assert "Keep this task across rollback" in request("http://127.0.0.1:18080", "/")
            shutil.copy(state / "report.json", output / "rollback.json")
            # Separate state models a first release with nothing to restore.
            first = Path(temporary) / "first"
            assert release(bad, first, start, verify) == 1
            assert json.loads((first / "report.json").read_text())["status"] == "manual-intervention"
            assert not (first / "current.json").exists()
            shutil.copy(first / "report.json", output / "first-release.json")
            print("PASS: digest deployment, CRUD smoke/cleanup, broken-image rollback, data persistence, first-release failure")
        finally:
            if active_env:
                subprocess.run(["docker", "compose", "-f", "docker-compose.aws.yml", "-p", project, "down"], env=active_env, check=False)
            for name in reversed(created):
                subprocess.run(["docker", "rm", "-f", "-v", name], check=False)


if __name__ == "__main__":
    main()
