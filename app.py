import json as json_module
import os
import re
import shutil
import time
import zipfile
import uuid
import asyncio
import aiofiles
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from core.task_store import TaskStore

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

TEMP_MAX_AGE_SECONDS = 3600  # 1 hour
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_ARCHIVE_ENTRIES = 20000
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 10 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRY_SIZE = 512 * 1024 * 1024
task_store = TaskStore(os.path.join(TEMP_DIR, "tasks.sqlite3"))


def validate_archive(zip_path: str):
    """Validate ZIP metadata before handing it to the encrypted parser."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Archive contains too many files")

            total_uncompressed = 0
            for info in entries:
                if info.is_dir():
                    continue
                if info.file_size > MAX_ARCHIVE_ENTRY_SIZE:
                    raise ValueError("Archive entry is too large")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                    raise ValueError("Archive expands beyond the allowed limit")
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid ZIP file or corrupted archive") from exc

async def cleanup_old_temp():
    """Periodically remove temp task directories older than TEMP_MAX_AGE_SECONDS."""
    while True:
        await asyncio.sleep(600)
        now = time.time()
        try:
            for name in os.listdir(TEMP_DIR):
                path = os.path.join(TEMP_DIR, name)
                if os.path.isdir(path):
                    task_id = name
                    state = task_store.get(task_id)
                    is_running = state and state.get("status") in {"queued", "parsing"}
                    updated_at = state.get("updated_at", 0) if state else 0
                    if not is_running and now - max(os.path.getmtime(path), updated_at) > TEMP_MAX_AGE_SECONDS:
                        shutil.rmtree(path, ignore_errors=True)
            for task_id in task_store.stale_ids(TEMP_MAX_AGE_SECONDS):
                task_store.delete(task_id)
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(cleanup_old_temp())
    yield
    task.cancel()

SESSION_SECRET = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET:
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("SESSION_SECRET_KEY must be configured in production")
    # Development convenience only; production must provide a stable secret.
    SESSION_SECRET = secrets.token_hex(32)
    print("Warning: SESSION_SECRET_KEY is not configured; using an ephemeral development key.")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=os.getenv("COOKIE_SECURE", "0") == "1",
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

from routers.strava import router as strava_router
app.include_router(strava_router, prefix="/api/strava")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.post("/api/parse")
async def parse_data(
    file: UploadFile = File(...),
    password: str = Form(...),
    start_date: str = Form(None),
    end_date: str = Form(None)
):
    """Upload file and start async parsing. Returns task_id immediately for SSE progress."""
    task_id = str(uuid.uuid4())
    task_dir = os.path.join(TEMP_DIR, task_id)
    upload_dir = os.path.join(task_dir, "upload")
    export_dir = os.path.join(task_dir, "export")

    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(export_dir, exist_ok=True)

    zip_path = os.path.join(upload_dir, "source.zip")

    total_size = 0
    async with aiofiles.open(zip_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                shutil.rmtree(task_dir, ignore_errors=True)
                return JSONResponse(
                    {"status": "error", "message": "File too large (max 2GB)"},
                    status_code=413
                )
            await buffer.write(chunk)

    sd = start_date.strip() if start_date else None
    ed = end_date.strip() if end_date else None
    for field_name, field_value in (("start_date", sd), ("end_date", ed)):
        if field_value:
            try:
                datetime.strptime(field_value, "%Y-%m-%d")
            except ValueError:
                shutil.rmtree(task_dir, ignore_errors=True)
                return JSONResponse(
                    {"status": "error", "code": "INVALID_DATE", "message": "Invalid date format"},
                    status_code=400,
                )
    if sd and ed and ed < sd:
        shutil.rmtree(task_dir, ignore_errors=True)
        return JSONResponse(
            {"status": "error", "code": "INVALID_DATE_RANGE", "message": "End date must be on or after start date"},
            status_code=400,
        )

    try:
        validate_archive(zip_path)
    except ValueError as exc:
        shutil.rmtree(task_dir, ignore_errors=True)
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

    # Persist the job inputs for the independent worker. The password is kept
    # outside the task database and removed by the worker after processing.
    task_token = secrets.token_urlsafe(32)
    task_store.create(task_id, task_token)
    token_path = os.path.join(task_dir, ".task-token")
    password_path = os.path.join(task_dir, ".password")
    job_path = os.path.join(task_dir, "job.json")
    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(task_token)
    with open(password_path, "w", encoding="utf-8") as password_file:
        password_file.write(password)
    with open(job_path, "w", encoding="utf-8") as job_file:
        json_module.dump({"start_date": sd, "end_date": ed}, job_file)
    for protected_path in (token_path, password_path, job_path):
        try:
            os.chmod(protected_path, 0o600)
        except OSError:
            pass

    return {"status": "accepted", "task_id": task_id, "task_token": task_token}

@app.get("/api/parse/progress/{task_id}")
async def parse_progress_sse(task_id: str, token: str = ""):
    """SSE stream for parse progress. Sends events until parsing completes."""
    if not re.match(r'^[0-9a-f\-]{36}$', task_id):
        return JSONResponse({"error": "Invalid task ID"}, status_code=400)

    async def event_stream():
        last_sent = None
        last_progress_time = time.time()  # 记录最后一次有进度的时间
        MAX_IDLE_SECONDS = 1800  # 30 分钟无进度更新则超时
        iteration = 0

        while True:
            iteration += 1
            # 检查是否长时间无进度更新
            if time.time() - last_progress_time > MAX_IDLE_SECONDS:
                yield f"data: {json_module.dumps({'status': 'error', 'error': 'Timeout: no progress for 30 minutes'})}\n\n"
                break

            state = task_store.get(task_id)
            if state is None:
                yield f"data: {json_module.dumps({'status': 'error', 'error': 'Task not found'})}\n\n"
                break
            if not secrets.compare_digest(state.get("task_token", ""), token):
                yield f"data: {json_module.dumps({'status': 'error', 'error': 'Unauthorized'})}\n\n"
                break
            state_copy = dict(state)

            payload = {
                "status": state_copy["status"],
                "current": state_copy["current"],
                "total": state_copy["total"],
                "activity": state_copy["activity"],
            }

            if state_copy["status"] == "success":
                payload["results"] = state_copy["results"]
                payload["message"] = state_copy.get("message", "")
                payload["download_url"] = state_copy.get("download_url")
                serialized = json_module.dumps(payload)
                yield f"data: {serialized}\n\n"
                break
            elif state_copy["status"] == "error":
                payload["error"] = state_copy.get("error", "Unknown error")
                yield f"data: {json_module.dumps(payload)}\n\n"
                break
            else:
                serialized = json_module.dumps(payload)
                if serialized != last_sent:
                    yield f"data: {serialized}\n\n"
                    last_sent = serialized
                    last_progress_time = time.time()  # 有进度更新时重置计时
                await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })

@app.get("/api/download/{task_id}")
async def download_results(task_id: str, token: str = ""):
    if not re.match(r'^[0-9a-f\-]{36}$', task_id):
        return JSONResponse({"error": "Invalid task ID"}, status_code=400)
    task_dir = os.path.join(TEMP_DIR, task_id)
    result_zip_path = os.path.join(task_dir, "strava_exports.zip")

    state = task_store.get(task_id)
    authorized = state and secrets.compare_digest(state.get("task_token", ""), token)
    if authorized and os.path.exists(result_zip_path):
        return FileResponse(
            result_zip_path,
            media_type="application/zip",
            filename="strava_exports.zip"
        )
    return JSONResponse({"error": "File not found or expired"}, status_code=404)
