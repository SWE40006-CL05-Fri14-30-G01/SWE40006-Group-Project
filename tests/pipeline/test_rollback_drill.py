import json

import pytest

from scripts import deploy


GOOD = {"image": "example/app@sha256:" + "a" * 64, "build_id": "good"}
NEW = {"image": "example/app@sha256:" + "b" * 64, "build_id": "candidate"}


def test_drill_rejects_candidate_but_verifies_recovery(tmp_path, monkeypatch):
    checks = []
    monkeypatch.setattr(deploy, "wait_ready", lambda base, build: checks.append(("ready", build)))
    monkeypatch.setattr(deploy, "smoke", lambda base, build: checks.append(("smoke", build)))
    deploy.verify_deployment("http://local", NEW, "test", NEW)
    deploy.atomic_json(tmp_path / "current.json", GOOD)
    deploy.require_rollback_target(tmp_path, NEW)
    activated = []
    result = deploy.release(NEW, tmp_path, activated.append,
        lambda item: deploy.verify_deployment("http://local", item, "production", NEW))
    assert result == 1
    assert activated == [NEW, GOOD]
    assert checks[-2:] == [("ready", "good"), ("smoke", "good")]
    assert json.loads((tmp_path / "current.json").read_text()) == GOOD
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "rolled-back-release-failed"


def test_drill_refuses_missing_or_identical_recovery_image(tmp_path):
    with pytest.raises(FileNotFoundError):
        deploy.require_rollback_target(tmp_path, NEW)
    deploy.atomic_json(tmp_path / "current.json", NEW)
    with pytest.raises(RuntimeError, match="different"):
        deploy.require_rollback_target(tmp_path, NEW)
