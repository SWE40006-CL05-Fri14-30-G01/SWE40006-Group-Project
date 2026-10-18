import json
from unittest.mock import Mock

import pytest

from scripts.deploy import release, validate_release
from scripts.check_reports import check
from scripts.smoke import find_task, smoke
from scripts.preflight import check as preflight

GOOD = {"image": "team/app@sha256:" + "a" * 64, "build_id": "good"}
BAD = {"image": "team/app@sha256:" + "b" * 64, "build_id": "bad"}


def test_failed_release_restores_prior_but_remains_failed(tmp_path):
    (tmp_path / "current.json").write_text(json.dumps(GOOD))
    start = Mock()
    verify = Mock(side_effect=[RuntimeError("broken"), None])
    assert release(BAD, tmp_path, start, verify) == 1
    assert [call.args[0] for call in start.call_args_list] == [BAD, GOOD]
    assert json.loads((tmp_path / "current.json").read_text()) == GOOD
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "rolled-back-release-failed"


def test_start_failure_also_rolls_back(tmp_path):
    (tmp_path / "current.json").write_text(json.dumps(GOOD))
    start = Mock(side_effect=[RuntimeError("docker failed"), None])
    assert release(BAD, tmp_path, start, Mock()) == 1
    assert start.call_count == 2


def test_first_release_failure_requires_intervention(tmp_path):
    assert release(BAD, tmp_path, Mock(side_effect=RuntimeError()), Mock()) == 1
    assert not (tmp_path / "current.json").exists()
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "manual-intervention"


def test_failed_recovery_requires_intervention(tmp_path):
    (tmp_path / "current.json").write_text(json.dumps(GOOD))
    verify = Mock(side_effect=RuntimeError())
    assert release(BAD, tmp_path, Mock(), verify) == 1
    assert verify.call_count == 2
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "manual-intervention"


def test_success_updates_current_only_after_verification(tmp_path):
    def verify(item):
        assert not (tmp_path / "current.json").exists()
    assert release(GOOD, tmp_path, Mock(), verify) == 0
    assert json.loads((tmp_path / "current.json").read_text()) == GOOD


def test_refuses_mutable_image_tag():
    with pytest.raises(ValueError):
        validate_release({"image": "team/app:latest", "build_id": "good"})


@pytest.mark.parametrize("xml", ['<testsuite/>', '<testsuite><testcase><skipped/></testcase></testsuite>', '<testsuite><testcase><failure/></testcase></testsuite>'])
def test_gate_rejects_empty_skipped_or_failed_suite(tmp_path, xml):
    report = tmp_path / "tests.xml"
    report.write_text(xml)
    with pytest.raises(ValueError):
        check(report)


def test_smoke_ignores_flash_messages_and_other_tasks():
    html = '<div class="alert">unique</div><div class="task-card"><div>other</div><form action="/delete/1"></form></div>'
    assert find_task(html, "unique") is None
    html += '<div class="task-card"><div>unique</div><form action="/delete/2"></form></div>'
    assert find_task(html, "unique") == "/delete/2"


def test_cleanup_runs_when_create_response_fails(monkeypatch):
    monkeypatch.setattr("scripts.smoke.uuid.uuid4", lambda: type("Id", (), {"hex": "unique"})())
    card = '<div class="task-card"><div>pipeline-smoke-unique</div><form action="/delete/42"></form></div>'
    request = Mock(side_effect=[json.dumps({"status": "healthy", "build_id": "good"}), "", RuntimeError("create response lost"), card, "", ""])
    monkeypatch.setattr("scripts.smoke.request", request)
    with pytest.raises(RuntimeError, match="create response lost"):
        smoke("http://localhost", "good")
    assert request.call_args_list[4].args == ("http://localhost", "/delete/42", {})


def configure_release(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    values = {"DOCKERHUB_IMAGE": "team/taskmanager", "DOCKERHUB_USERNAME": "team",
              "DOCKERHUB_TOKEN": "dummy", "DOCKERHUB_PULL_TOKEN": "dummy",
              "TEST_DATABASE_URL": "postgresql://test:dummy@db/test",
              "PROD_DATABASE_URL": "postgresql://prod:dummy@db/prod",
              "TEST_SECRET_KEY": "test-dummy", "PROD_SECRET_KEY": "prod-dummy"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_preflight_blocks_missing_acceptance_suites(monkeypatch, tmp_path):
    configure_release(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="acceptance suite is missing"):
        preflight()


def test_preflight_blocks_shared_database(monkeypatch, tmp_path):
    configure_release(monkeypatch, tmp_path)
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://prod:dummy@db/test")
    with pytest.raises(ValueError, match="distinct"):
        preflight()


def test_preflight_blocks_missing_secret(monkeypatch, tmp_path):
    configure_release(monkeypatch, tmp_path)
    monkeypatch.delenv("DOCKERHUB_TOKEN")
    with pytest.raises(ValueError, match="DOCKERHUB_TOKEN"):
        preflight()


def test_logging_failure_does_not_prevent_recovery(tmp_path):
    (tmp_path / "current.json").write_text(json.dumps(GOOD))
    start = Mock()
    assert release(BAD, tmp_path, start, Mock(side_effect=[RuntimeError(), None]),
                   Mock(side_effect=OSError())) == 1
    assert start.call_count == 2
    assert json.loads((tmp_path / "report.json").read_text())["diagnostics_failed"]
