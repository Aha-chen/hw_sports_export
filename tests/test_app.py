import zipfile
import io
import uuid

import pytest

from app import validate_archive
from fastapi.testclient import TestClient
from app import app, task_store


def test_validate_archive_accepts_small_zip(tmp_path):
    archive_path = tmp_path / "small.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data.json", "[]")

    validate_archive(str(archive_path))


def test_validate_archive_rejects_invalid_zip(tmp_path):
    archive_path = tmp_path / "invalid.zip"
    archive_path.write_bytes(b"not a zip")

    with pytest.raises(ValueError, match="Invalid ZIP"):
        validate_archive(str(archive_path))


def test_health_endpoint_and_invalid_upload():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        response = client.post(
            "/api/parse",
            files={"file": ("input.zip", io.BytesIO(b"not a zip"), "application/zip")},
            data={"password": "secret"},
        )
        assert response.status_code == 400
        assert response.json()["status"] == "error"
        assert response.json()["code"] == "INVALID_ARCHIVE"


def test_parse_rejects_invalid_date_range():
    with TestClient(app) as client:
        response = client.post(
            "/api/parse",
            files={"file": ("input.zip", io.BytesIO(b"not a zip"), "application/zip")},
            data={"password": "secret", "start_date": "2026-07-15", "end_date": "2026-07-14"},
        )
        # 日期校验先于归档校验，让用户优先收到可直接修正的日期范围错误。
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_DATE_RANGE"


def test_sse_requires_task_token():
    task_id = str(uuid.uuid4())
    task_store.create(task_id, "secret-token")
    task_store.update(task_id, status="success", results=[], message="done")
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/parse/progress/{task_id}?token=wrong")
            assert response.status_code == 200
            assert "TASK_UNAUTHORIZED" in response.text
    finally:
        task_store.delete(task_id)


def test_sse_returns_partial_success_warnings():
    task_id = str(uuid.uuid4())
    task_store.create(task_id, "secret-token")
    task_store.update(
        task_id,
        status="partial_success",
        results=[{"filename": "activity.tcx"}],
        warnings=[
            {
                "code": "ACTIVITY_PARSE_FAILED",
                "scope": "activity",
                "source": "data.json#1",
                "message": "Activity could not be converted",
            }
        ],
        manifest={
            "schema_version": 1,
            "status": "partial_success",
            "counts": {
                "total": 2,
                "succeeded": 1,
                "skipped": 0,
                "date_filtered": 0,
                "no_exportable": 0,
                "failed": 1,
                "failed_files": 0,
                "warnings": 1,
            },
        },
        message="Processed with one warning.",
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/parse/progress/{task_id}?token=secret-token")
            assert response.status_code == 200
            assert '"status": "partial_success"' in response.text
            assert '"code": "ACTIVITY_PARSE_FAILED"' in response.text
            assert '"manifest":' in response.text
    finally:
        task_store.delete(task_id)


def test_sse_error_includes_warnings_and_manifest():
    task_id = str(uuid.uuid4())
    task_store.create(task_id, "secret-token")
    task_store.update(
        task_id,
        status="error",
        error="NO_MATCHING_ACTIVITIES",
        warnings=[],
        manifest={
            "schema_version": 1,
            "status": "error",
            "counts": {
                "total": 1,
                "succeeded": 0,
                "skipped": 1,
                "date_filtered": 1,
                "no_exportable": 0,
                "failed": 0,
                "failed_files": 0,
                "warnings": 0,
            },
            "activities": [],
            "issues": [],
        },
        message="",
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/parse/progress/{task_id}?token=secret-token")
            assert response.status_code == 200
            assert '"status": "error"' in response.text
            assert '"error": "NO_MATCHING_ACTIVITIES"' in response.text
            assert '"warnings":' in response.text
            assert '"manifest":' in response.text
            assert '"date_filtered": 1' in response.text
    finally:
        task_store.delete(task_id)
