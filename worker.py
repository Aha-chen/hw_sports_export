"""Independent parser worker for the Huawei export queue."""

import json
import os
import shutil
import signal
import time
import uuid
import zipfile

from core.parser import HuaweiParseError, parse_huawei_zip
from core.task_store import TaskStore


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
POLL_INTERVAL = float(os.getenv("WORKER_POLL_INTERVAL", "1"))
task_store = TaskStore(os.path.join(TEMP_DIR, "tasks.sqlite3"))
running = True

# 无成功结果时的任务级错误码优先级：按问题严重度与可操作性排序，不依赖 issue 收集顺序。
_TASK_ERROR_CODE_PRIORITY = (
    "UNSUPPORTED_EXPORT_SCHEMA",
    "DATA_FILE_INVALID",
    "DATA_FILE_READ_FAILED",
    "ACTIVITY_PARSE_FAILED",
)


def resolve_task_error_code(outcome):
    """在无成功结果时生成稳定的任务级错误码。

    规则：
    1. 存在结构化 issue 时，按固定优先级选取汇总码（与并发收集顺序无关）；
    2. 无 issue 且全部为日期过滤跳过 → NO_MATCHING_ACTIVITIES；
    3. 其余空结果 → NO_ACTIVITIES。
    """
    issue_codes = {issue.code for issue in outcome.issues}
    for code in _TASK_ERROR_CODE_PRIORITY:
        if code in issue_codes:
            return code

    if (
        outcome.total_activities > 0
        and not outcome.results
        and not outcome.issues
        and outcome.date_filtered_activities > 0
        and outcome.no_exportable_activities == 0
        and outcome.date_filtered_activities == outcome.skipped_activities
    ):
        return "NO_MATCHING_ACTIVITIES"

    return "NO_ACTIVITIES"


def build_manifest(outcome, status):
    """生成稳定且不包含轨迹明细的任务结果清单。"""
    warnings = [issue.as_dict() for issue in outcome.issues]
    # failed：活动级失败数；failed_files：文件级问题数（不计入活动 failed）。
    failed_activities = sum(1 for warning in warnings if warning.get("scope") == "activity")
    failed_files = sum(1 for warning in warnings if warning.get("scope") == "file")
    succeeded_activities = len(outcome.results)
    skipped_activities = outcome.skipped_activities
    counted_total = succeeded_activities + failed_activities + skipped_activities
    total_activities = max(outcome.total_activities, counted_total)

    # manifest 只保留排障和核对所需摘要，避免复制完整轨迹、心率曲线等健康数据。
    activities = [
        {
            key: result[key]
            for key in (
                "filename",
                "sport",
                "date",
                "distance",
                "duration",
                "points",
            )
            if key in result
        }
        for result in outcome.results
    ]
    return {
        "schema_version": 1,
        "status": status,
        "counts": {
            "total": total_activities,
            "succeeded": succeeded_activities,
            "skipped": skipped_activities,
            "date_filtered": outcome.date_filtered_activities,
            "no_exportable": outcome.no_exportable_activities,
            "failed": failed_activities,
            "failed_files": failed_files,
            "warnings": len(warnings),
        },
        "activities": activities,
        "issues": warnings,
    }


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

        outcome = parse_huawei_zip(
            zip_path,
            password,
            export_dir,
            job.get("start_date"),
            job.get("end_date"),
            progress_callback,
        )
        results = outcome.results
        warnings = [issue.as_dict() for issue in outcome.issues]

        if not results:
            error_code = resolve_task_error_code(outcome)
            manifest = build_manifest(outcome, "error")
            task_store.update(
                task_id,
                status="error",
                error=error_code,
                warnings=warnings,
                manifest=manifest,
            )
            shutil.rmtree(task_dir, ignore_errors=True)
            return

        # 有可下载结果但存在任意 issue 时记为部分成功（与 SPEC 对齐：无 issue 才是 success）。
        final_status = "partial_success" if warnings else "success"
        manifest = build_manifest(outcome, final_status)
        manifest_path = os.path.join(task_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)

        result_zip_path = os.path.join(task_dir, "strava_exports.zip")
        with zipfile.ZipFile(result_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for result in results:
                file_path = os.path.join(export_dir, result["filename"])
                archive.write(file_path, result["filename"])
            archive.write(manifest_path, "manifest.json")

        task_store.update(
            task_id,
            status=final_status,
            results=results,
            warnings=warnings,
            manifest=manifest,
            message=(
                f"Processed {len(results)} activities with {len(warnings)} issue(s)."
                if warnings
                else f"Successfully processed {len(results)} activities."
            ),
            download_url=f"/api/download/{task_id}?token={task['task_token']}" if results else None,
        )
        # The source archive and password are no longer needed after success.
        shutil.rmtree(os.path.join(task_dir, "upload"), ignore_errors=True)
        for path in (password_path, job_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
    except HuaweiParseError as exc:
        task_store.update(task_id, status="error", error=exc.code)
        shutil.rmtree(task_dir, ignore_errors=True)
    except Exception:
        task_store.update(task_id, status="error", error="INTERNAL_ERROR")
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
