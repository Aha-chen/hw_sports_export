from core.task_store import TaskStore
from core.strava_store import StravaStore
import json
import uuid
import zipfile

import worker
from core.parser import IncorrectPasswordError, ParseIssue, ParseOutcome
from worker import resolve_task_error_code


def test_task_store_persists_and_recovers(tmp_path):
    store = TaskStore(str(tmp_path / "tasks.sqlite3"))
    store.create("task-1", "token")
    store.update("task-1", current=2, total=3, activity="Running")

    assert store.get("task-1")["current"] == 2
    store.recover_interrupted()
    assert store.get("task-1")["status"] == "queued"
    claimed = store.claim_next("worker-1")
    assert claimed["task_id"] == "task-1"
    assert claimed["status"] == "parsing"
    assert store.claim_next("worker-2") is None


def test_strava_tokens_are_server_side(tmp_path):
    store = StravaStore(str(tmp_path / "strava.sqlite3"))
    store.save("session-1", "access", "refresh", 123, "Athlete")

    session = store.get("session-1")
    assert session["refresh_token"] == "refresh"
    store.delete("session-1")
    assert store.get("session-1") is None


def test_worker_processes_claimed_task(tmp_path, monkeypatch):
    task_id = str(uuid.uuid4())
    task_dir = tmp_path / task_id
    (task_dir / "upload").mkdir(parents=True)
    (task_dir / "export").mkdir()
    (task_dir / "upload" / "source.zip").write_bytes(b"zip")
    (task_dir / ".password").write_text("secret")
    (task_dir / "job.json").write_text(json.dumps({"start_date": None, "end_date": None}))
    (task_dir / ".task-token").write_text("token")

    store = worker.TaskStore(str(tmp_path / "tasks.sqlite3"))
    store.create(task_id, "token")
    monkeypatch.setattr(worker, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "task_store", store)

    def fake_parser(_zip, _password, export_dir, *_args):
        (tmp_path / task_id / "export" / "strava_Run_20240101_000000.tcx").write_text("<tcx />")
        return ParseOutcome(
            results=[{"filename": "strava_Run_20240101_000000.tcx", "sport": "Running"}],
            issues=[],
            total_activities=1,
        )

    monkeypatch.setattr(worker, "parse_huawei_zip", fake_parser)
    worker.process_task(store.claim_next("worker-1"))

    state = store.get(task_id)
    assert state["status"] == "success"
    assert state["manifest"]["counts"]["succeeded"] == 1
    assert (task_dir / "strava_exports.zip").exists()
    with zipfile.ZipFile(task_dir / "strava_exports.zip") as archive:
        assert "manifest.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest == state["manifest"]


def test_worker_does_not_report_empty_result_as_success(tmp_path, monkeypatch):
    task_id = str(uuid.uuid4())
    task_dir = tmp_path / task_id
    (task_dir / "upload").mkdir(parents=True)
    (task_dir / "export").mkdir()
    (task_dir / "upload" / "source.zip").write_bytes(b"zip")
    (task_dir / ".password").write_text("secret")
    (task_dir / "job.json").write_text(json.dumps({"start_date": None, "end_date": None}))

    store = worker.TaskStore(str(tmp_path / "tasks.sqlite3"))
    store.create(task_id, "token")
    monkeypatch.setattr(worker, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "task_store", store)
    monkeypatch.setattr(
        worker,
        "parse_huawei_zip",
        lambda *_args: ParseOutcome(results=[], issues=[]),
    )

    worker.process_task(store.claim_next("worker-1"))

    assert store.get(task_id)["status"] == "error"
    assert store.get(task_id)["error"] == "NO_ACTIVITIES"


def test_resolve_task_error_code_date_filtered_is_stable():
    outcome = ParseOutcome(
        results=[],
        issues=[],
        total_activities=2,
        skipped_activities=2,
        date_filtered_activities=2,
        no_exportable_activities=0,
    )
    assert resolve_task_error_code(outcome) == "NO_MATCHING_ACTIVITIES"


def test_resolve_task_error_code_prefers_stable_priority_over_issue_order():
    outcome = ParseOutcome(
        results=[],
        issues=[
            ParseIssue(
                code="ACTIVITY_PARSE_FAILED",
                scope="activity",
                source="a#0",
                message="fail",
            ),
            ParseIssue(
                code="DATA_FILE_INVALID",
                scope="file",
                source="b.json",
                message="bad",
            ),
            ParseIssue(
                code="UNSUPPORTED_EXPORT_SCHEMA",
                scope="file",
                source="c.json",
                message="schema",
            ),
        ],
        total_activities=1,
    )
    # 优先级高于并发收集顺序：schema > invalid file > activity fail
    assert resolve_task_error_code(outcome) == "UNSUPPORTED_EXPORT_SCHEMA"


def test_worker_reports_no_matching_activities_for_date_filter(tmp_path, monkeypatch):
    task_id = str(uuid.uuid4())
    task_dir = tmp_path / task_id
    (task_dir / "upload").mkdir(parents=True)
    (task_dir / "export").mkdir()
    (task_dir / "upload" / "source.zip").write_bytes(b"zip")
    (task_dir / ".password").write_text("secret")
    (task_dir / "job.json").write_text(
        json.dumps({"start_date": "2099-01-01", "end_date": None})
    )

    store = worker.TaskStore(str(tmp_path / "tasks.sqlite3"))
    store.create(task_id, "token")
    monkeypatch.setattr(worker, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "task_store", store)
    monkeypatch.setattr(
        worker,
        "parse_huawei_zip",
        lambda *_args: ParseOutcome(
            results=[],
            issues=[],
            total_activities=1,
            skipped_activities=1,
            date_filtered_activities=1,
            no_exportable_activities=0,
        ),
    )

    worker.process_task(store.claim_next("worker-1"))

    state = store.get(task_id)
    assert state["status"] == "error"
    assert state["error"] == "NO_MATCHING_ACTIVITIES"
    assert state["manifest"]["counts"]["date_filtered"] == 1


def test_worker_persists_incorrect_password_error_code(tmp_path, monkeypatch):
    task_id = str(uuid.uuid4())
    task_dir = tmp_path / task_id
    (task_dir / "upload").mkdir(parents=True)
    (task_dir / "export").mkdir()
    (task_dir / "upload" / "source.zip").write_bytes(b"zip")
    (task_dir / ".password").write_text("wrong")
    (task_dir / "job.json").write_text(json.dumps({"start_date": None, "end_date": None}))

    store = worker.TaskStore(str(tmp_path / "tasks.sqlite3"))
    store.create(task_id, "token")
    monkeypatch.setattr(worker, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "task_store", store)

    def reject_password(*_args):
        raise IncorrectPasswordError("Incorrect extraction password provided")

    monkeypatch.setattr(worker, "parse_huawei_zip", reject_password)
    worker.process_task(store.claim_next("worker-1"))

    state = store.get(task_id)
    assert state["status"] == "error"
    assert state["error"] == "INCORRECT_PASSWORD"


def test_worker_reports_partial_success(tmp_path, monkeypatch):
    task_id = str(uuid.uuid4())
    task_dir = tmp_path / task_id
    (task_dir / "upload").mkdir(parents=True)
    (task_dir / "export").mkdir()
    (task_dir / "upload" / "source.zip").write_bytes(b"zip")
    (task_dir / ".password").write_text("secret")
    (task_dir / "job.json").write_text(json.dumps({"start_date": None, "end_date": None}))
    (task_dir / ".task-token").write_text("token")

    store = worker.TaskStore(str(tmp_path / "tasks.sqlite3"))
    store.create(task_id, "token")
    monkeypatch.setattr(worker, "TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(worker, "task_store", store)

    def fake_parser(_zip, _password, export_dir, *_args):
        (tmp_path / task_id / "export" / "strava_Run_20240101_000000.tcx").write_text("<tcx />")
        return ParseOutcome(
            results=[{"filename": "strava_Run_20240101_000000.tcx", "sport": "Running"}],
            issues=[
                ParseIssue(
                    code="ACTIVITY_PARSE_FAILED",
                    scope="activity",
                    source="data.json#1",
                    message="Activity could not be converted",
                )
            ],
            total_activities=2,
        )

    monkeypatch.setattr(worker, "parse_huawei_zip", fake_parser)
    worker.process_task(store.claim_next("worker-1"))

    state = store.get(task_id)
    assert state["status"] == "partial_success"
    assert state["warnings"][0]["code"] == "ACTIVITY_PARSE_FAILED"
    assert state["manifest"]["status"] == "partial_success"
    assert state["manifest"]["counts"] == {
        "total": 2,
        "succeeded": 1,
        "skipped": 0,
        "date_filtered": 0,
        "no_exportable": 0,
        "failed": 1,
        "failed_files": 0,
        "warnings": 1,
    }
    assert (task_dir / "strava_exports.zip").exists()
