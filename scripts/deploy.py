"""Linux runner deployment with persistent state and bounded recovery.

Credentials are inherited through the environment, never command-line arguments.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from scripts.smoke import smoke, wait_ready

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.aws.yml"


def command(args, env):
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Docker errors may contain interpolated configuration; don't print them.
        raise RuntimeError("Container operation failed: " + args[0])
    return result.stdout.strip()


def validate_release(release):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]*@sha256:[a-f0-9]{64}", release["image"]):
        raise ValueError("IMAGE_REF must be a repository@sha256 digest")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", release["build_id"]):
        raise ValueError("Invalid build identifier")


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def activate(release, project, base_env):
    validate_release(release)
    env = dict(base_env, IMAGE_REF=release["image"], BUILD_ID=release["build_id"])
    prefix = ["docker", "compose", "-f", str(COMPOSE), "-p", project]
    # Reuse cached immutable images, particularly when registry access fails during recovery.
    try:
        command(["docker", "image", "inspect", release["image"]], env)
    except RuntimeError:
        command(prefix + ["pull", "web"], env)
    command(prefix + ["up", "-d", "--no-build", "--force-recreate", "web"], env)
    container = command(prefix + ["ps", "-q", "web"], env)
    actual = command(["docker", "inspect", "--format", "{{.Image}}", container], env)
    expected = command(["docker", "image", "inspect", "--format", "{{.Id}}", release["image"]], env)
    if actual != expected:
        raise RuntimeError("Running container does not match requested image")


def release(candidate, state_dir, activate_fn, verify_fn, diagnostics=lambda stage: None):
    """Return a failure even when the prior application is successfully restored."""
    state_dir.mkdir(parents=True, exist_ok=True)
    current = state_dir / "current.json"
    previous = json.loads(current.read_text()) if current.exists() else None
    if previous:
        validate_release(previous)
    atomic_json(state_dir / "previous.json", previous)
    report = {"candidate": candidate, "previous": previous, "status": "deploying"}
    atomic_json(state_dir / "report.json", report)
    try:
        activate_fn(candidate)
        verify_fn(candidate)
        atomic_json(current, candidate)
        report["status"] = "success"
        code = 0
    except Exception as exc:
        try:
            diagnostics("candidate")
        except Exception:
            report["diagnostics_failed"] = True
        report["failure_type"] = type(exc).__name__
        report["status"] = "manual-intervention"
        code = 1
        if previous:
            try:
                activate_fn(previous)
                verify_fn(previous)
                report["status"] = "rolled-back-release-failed"
            except Exception as recovery:
                report["recovery_failure_type"] = type(recovery).__name__
                try:
                    diagnostics("recovery")
                except Exception:
                    report["recovery_diagnostics_failed"] = True
    atomic_json(state_dir / "report.json", report)
    print("Release result: " + report["status"])
    return code


def require_rollback_target(state_dir, candidate):
    """Temporary drill: refuse to replace production without a recovery image."""
    previous = json.loads((state_dir / "current.json").read_text())
    validate_release(previous)
    if previous["image"] == candidate["image"]:
        raise RuntimeError("Rollback drill requires a different previously verified image")


def verify_deployment(base, item, environment, candidate):
    wait_ready(base, item["build_id"])
    smoke(base, item["build_id"])
    # TEMPORARY ROLLBACK DRILL: reject only the new production candidate.
    # Recovery still performs the real smoke test against the previous image.
    if environment == "production" and item == candidate:
        print("ROLLBACK DRILL: intentionally rejecting the new production candidate after smoke checks.")
        raise RuntimeError("Intentional production verification failure for rollback drill")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["test", "production"], required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    for name in ["DATABASE_URL", "SECRET_KEY", "IMAGE_REF", "BUILD_ID"]:
        if not env.get(name):
            raise ValueError("Missing " + name)
    if not env["DATABASE_URL"].startswith(("postgresql://", "postgresql+psycopg2://")):
        raise ValueError("Deployments require PostgreSQL")
    candidate = {"image": env["IMAGE_REF"], "build_id": env["BUILD_ID"]}
    validate_release(candidate)
    port = int(env.get("APP_PORT", "80"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid application port")
    base = "http://127.0.0.1:" + str(port)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    # The workflow lock spans both servers; this also guards direct script usage.
    import fcntl
    with (args.state_dir / "deploy.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        if args.environment == "production":
            require_rollback_target(args.state_dir, candidate)

        def verify(item):
            verify_deployment(base, item, args.environment, candidate)

        def diagnostics(stage):
            output = command(["docker", "compose", "-f", str(COMPOSE), "-p",
                              "taskmanager-" + args.environment, "logs", "--no-color", "--tail", "200", "web"], env)
            # Never archive credentials if an exception included connection details.
            from urllib.parse import urlsplit, unquote
            password = unquote(urlsplit(env["DATABASE_URL"]).password or "")
            for value in [env["DATABASE_URL"], env["SECRET_KEY"], password]:
                if value:
                    output = output.replace(value, "[REDACTED]")
            (args.state_dir / (stage + ".log")).write_text(output)

        return release(candidate, args.state_dir,
                       lambda item: activate(item, "taskmanager-" + args.environment, env), verify, diagnostics)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Deployment could not complete: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
