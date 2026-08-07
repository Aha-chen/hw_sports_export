import os
import re
import time
import secrets
import httpx
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.templating import Jinja2Templates
from core.strava_store import StravaStore

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "")
strava_session_store = StravaStore(os.path.join(TEMP_DIR, "strava_sessions.sqlite3"))


def is_configured() -> bool:
    return bool(STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET)


async def ensure_valid_token(request: Request) -> str:
    """Get a valid access token, refreshing if expired."""
    session_id = request.session.get("strava_session_id")
    session = strava_session_store.get(session_id) or {}
    access_token = session.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Not connected to Strava")

    expires_at = session.get("expires_at", 0)
    if time.time() >= expires_at:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": STRAVA_CLIENT_ID,
                    "client_secret": STRAVA_CLIENT_SECRET,
                    "refresh_token": session.get("refresh_token", ""),
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code != 200:
            strava_session_store.delete(session_id)
            request.session.pop("strava_session_id", None)
            raise HTTPException(status_code=401, detail="Token refresh failed, please reconnect")
        tokens = resp.json()
        strava_session_store.save(
            session_id,
            tokens["access_token"],
            tokens["refresh_token"],
            tokens["expires_at"],
            session.get("athlete_name", ""),
        )
        return tokens["access_token"]

    return access_token


@router.get("/status")
async def strava_status(request: Request):
    if not is_configured():
        return {"configured": False, "connected": False}

    session_id = request.session.get("strava_session_id")
    session = strava_session_store.get(session_id) or {}
    access_token = session.get("access_token")
    if not access_token:
        return {"configured": True, "connected": False}

    return {
        "configured": True,
        "connected": True,
        "athlete_name": session.get("athlete_name", ""),
    }


@router.get("/authorize")
async def strava_authorize(request: Request):
    if not is_configured():
        raise HTTPException(status_code=400, detail="Strava not configured")

    state = secrets.token_urlsafe(32)
    request.session["strava_oauth_state"] = state

    # Build redirect URI from the current request
    redirect_uri = STRAVA_REDIRECT_URI or (
        str(request.base_url).rstrip("/") + "/api/strava/callback"
    )

    url = (
        STRAVA_AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": STRAVA_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": "activity:write",
                "state": state,
            }
        )
    )
    return {"url": url}


@router.get("/callback", response_class=HTMLResponse)
async def strava_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    expected_state = request.session.get("strava_oauth_state", "")
    if not state or not secrets.compare_digest(state, expected_state):
        return templates.TemplateResponse(
            "strava_callback.html",
            {
                "request": request,
                "success": False,
                "error": "Invalid state parameter",
            },
        )
    request.session.pop("strava_oauth_state", None)

    if error:
        return templates.TemplateResponse(
            "strava_callback.html",
            {
                "request": request,
                "success": False,
                "error": error,
            },
        )

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        return templates.TemplateResponse(
            "strava_callback.html",
            {
                "request": request,
                "success": False,
                "error": "Failed to exchange authorization code",
            },
        )

    data = resp.json()
    athlete = data.get("athlete", {})
    athlete_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    session_id = secrets.token_urlsafe(32)
    strava_session_store.save(
        session_id,
        data["access_token"],
        data["refresh_token"],
        data["expires_at"],
        athlete_name,
    )
    request.session["strava_session_id"] = session_id

    return templates.TemplateResponse(
        "strava_callback.html",
        {
            "request": request,
            "success": True,
            "athlete_name": athlete_name,
        },
    )


@router.post("/upload")
async def strava_upload(request: Request):
    body = await request.json()
    task_id = body.get("task_id", "")
    filename = body.get("filename", "")
    task_token = body.get("task_token", "")

    # Validate task_id (UUID format)
    if not re.match(r"^[0-9a-f\-]{36}$", task_id):
        raise HTTPException(status_code=400, detail="Invalid task ID")

    # Validate filename using whitelist regex (TCX format: strava_{sport}_{date}.tcx)
    # 允许的格式：strava_SportType_YYYYMMDD_HHMMSS.tcx 或 Indoor_Running_YYYYMMDD_HHMMSS.tcx
    if not re.match(r"^[a-zA-Z0-9_\-]+_[0-9]{8}_[0-9]{6}\.tcx$", filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    # 构建文件路径并验证路径安全性
    file_path = os.path.join(TEMP_DIR, task_id, "export", filename)
    # 确保路径不会逃逸出预期的目录
    expected_base = os.path.join(TEMP_DIR, task_id, "export")
    token_path = os.path.join(TEMP_DIR, task_id, ".task-token")
    try:
        with open(token_path, encoding="utf-8") as token_file:
            expected_token = token_file.read().strip()
    except OSError:
        raise HTTPException(status_code=404, detail="Task not found or session expired")
    if not task_token or not secrets.compare_digest(expected_token, task_token):
        raise HTTPException(status_code=401, detail="Unauthorized task")
    real_path = os.path.realpath(file_path)
    try:
        if os.path.commonpath([real_path, os.path.realpath(expected_base)]) != os.path.realpath(
            expected_base
        ):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal detected")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or session expired")

    access_token = await ensure_valid_token(request)

    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{STRAVA_API_BASE}/uploads",
                headers={"Authorization": f"Bearer {access_token}"},
                files={"file": (filename, f, "application/xml")},
                data={"data_type": "tcx"},
                timeout=60.0,
            )

    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "60")
        return JSONResponse(
            {"status": "rate_limited", "retry_after": int(retry_after)},
            status_code=429,
        )

    if resp.status_code not in (200, 201):
        return JSONResponse(
            {"status": "error", "error": resp.text},
            status_code=resp.status_code,
        )

    data = resp.json()
    return {"upload_id": data.get("id"), "status": "processing"}


@router.get("/upload-status/{upload_id}")
async def strava_upload_status(request: Request, upload_id: int):
    access_token = await ensure_valid_token(request)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/uploads/{upload_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    if resp.status_code != 200:
        return {"status": "error", "error": "Failed to check upload status"}

    data = resp.json()
    activity_id = data.get("activity_id")
    error_str = data.get("error") or ""

    if activity_id:
        return {"status": "ready", "activity_id": activity_id}
    if "duplicate" in error_str.lower():
        return {"status": "duplicate", "error": error_str}
    if error_str:
        return {"status": "error", "error": error_str}
    return {"status": "processing"}


@router.post("/disconnect")
async def strava_disconnect(request: Request):
    session_id = request.session.pop("strava_session_id", None)
    if session_id:
        strava_session_store.delete(session_id)
    return {"ok": True}
