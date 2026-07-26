"""Independent parser worker for the Huawei export queue."""

import json
import os
import shutil
import signal
import time
import uuid
import zipfile

from core.parser import parse_huawei_zip
from core.task_store import TaskStore


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
POLL_INTERVAL = float(os.getenv("WORKER_POLL_INTERVAL", "1"))
task_store = TaskStore(os.path.join(TEMP_DIR, "tasks.sqlite3"))
running = True


def stop_worker(*_args):
    global running
    running = False


def process_task(task):
    task_id = task["task_id"]
    task_dir = os.path.join(TEMP_DIR, task_id)
    zip_path = os.path.join(task_dir, "upload", "source.zip")
    export_dir = os.path.join(task_dir, "export")
    password_path = os.path.join(task_dir, ".password")
    job_path = os.path.join(task_dir, "job.json")

    try:
        with open(password_path, encoding="utf-8") as password_file:
            password = password_file.read()
        with open(job_path, encoding="utf-8") as job_file:
            job = json.load(job_file)

        def progress_callback(current, total, activity):
            task_store.update(task_id, current=current, total=total, activity=activity)
            task_store.touch_claim(task_id, task["worker_id"])

        results = parse_huawei_zip(
            zip_path,
            password,
            export_dir,
            job.get("start_date"),
            job.get("end_date"),
            progress_callback,
        )

        if not results:
            task_store.update(task_id, status="error", error="NO_ACTIVITIES")
            shutil.rmtree(task_dir, ignore_errors=True)
            return

        result_zip_path = os.path.join(task_dir, "strava_exports.zip")
        with zipfile.ZipFile(result_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for result in results:
                file_path = os.path.join(export_dir, result["filename"])
                archive.write(file_path, result["filename"])

        task_store.update(
            task_id,
            status="success",
            results=results,
            message=f"Successfully processed {len(results)} activities.",
            download_url=f"/api/download/{task_id}?token={task['task_token']}" if results else None,
        )
        # The source archive and password are no longer needed after success.
        shutil.rmtree(os.path.join(task_dir, "upload"), ignore_errors=True)
        for path in (password_path, job_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
    except Exception:
        task_store.update(task_id, status="error", error="Unable to process archive")
        shutil.rmtree(task_dir, ignore_errors=True)


def main():
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    task_store.recover_interrupted()
    worker_id = f"worker-{uuid.uuid4()}"
    while running:
        task = task_store.claim_next(worker_id)
        if task is None:
            time.sleep(POLL_INTERVAL)
            continue
        process_task(task)


if __name__ == "__main__":
    main()
