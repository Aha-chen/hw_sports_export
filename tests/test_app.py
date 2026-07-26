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


def test_parse_rejects_invalid_date_range():
    with TestClient(app) as client:
        response = client.post(
            "/api/parse",
            files={"file": ("input.zip", io.BytesIO(b"not a zip"), "application/zip")},
            data={"password": "secret", "start_date": "2026-07-15", "end_date": "2026-07-14"},
        )
        # Date validation happens before archive validation so the user gets
        # the actionable date-range error.
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
            assert "Unauthorized" in response.text
    finally:
        task_store.delete(task_id)
