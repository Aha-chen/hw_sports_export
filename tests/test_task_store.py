from core.task_store import TaskStore
from core.strava_store import StravaStore
import json
import uuid

import worker


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
        return [{"filename": "strava_Run_20240101_000000.tcx", "sport": "Running"}]

    monkeypatch.setattr(worker, "parse_huawei_zip", fake_parser)
    worker.process_task(store.claim_next("worker-1"))

    assert store.get(task_id)["status"] == "success"
    assert (task_dir / "strava_exports.zip").exists()


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
    monkeypatch.setattr(worker, "parse_huawei_zip", lambda *_args: [])

    worker.process_task(store.claim_next("worker-1"))

    assert store.get(task_id)["status"] == "error"
    assert store.get(task_id)["error"] == "NO_ACTIVITIES"
