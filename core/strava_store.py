"""Server-side persistence for Strava OAuth credentials."""

import os
import sqlite3
import time


class StravaStore:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strava_sessions (
                    session_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    athlete_name TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL
                )
            """)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, session_id):
        if not session_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM strava_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def save(self, session_id, access_token, refresh_token, expires_at, athlete_name=""):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strava_sessions
                    (session_id, access_token, refresh_token, expires_at, athlete_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    access_token=excluded.access_token,
                    refresh_token=excluded.refresh_token,
                    expires_at=excluded.expires_at,
                    athlete_name=excluded.athlete_name,
                    updated_at=excluded.updated_at
            """,
                (session_id, access_token, refresh_token, expires_at, athlete_name, time.time()),
            )

    def delete(self, session_id):
        if not session_id:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM strava_sessions WHERE session_id = ?", (session_id,))
