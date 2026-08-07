"""Small SQLite-backed task store shared by all web workers on one volume."""

import json
import os
import sqlite3
import time


class TaskStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    activity TEXT NOT NULL DEFAULT '',
                    results TEXT,
                    warnings TEXT,
                    manifest TEXT,
                    error TEXT,
                    message TEXT,
                    download_url TEXT,
                    task_token TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    worker_id TEXT,
                    claimed_at REAL,
                    attempts INTEGER NOT NULL DEFAULT 0
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            for name, definition in {
                "worker_id": "TEXT",
                "claimed_at": "REAL",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "warnings": "TEXT",
                "manifest": "TEXT",
            }.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        state = dict(row)
        state["results"] = json.loads(state["results"]) if state["results"] else None
        state["warnings"] = json.loads(state["warnings"]) if state["warnings"] else []
        state["manifest"] = json.loads(state["manifest"]) if state["manifest"] else None
        return state

    def create(self, task_id, task_token, status="queued"):
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tasks(task_id, status, task_token, updated_at) VALUES (?, ?, ?, ?)",
                (task_id, status, task_token, now),
            )

    def get(self, task_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._decode(row)

    def update(self, task_id, **changes):
        if not changes:
            return False
        for json_field in ("results", "warnings", "manifest"):
            if json_field in changes:
                changes[json_field] = json.dumps(changes[json_field], ensure_ascii=False)
        changes["updated_at"] = time.time()
        allowed = {
            "status",
            "current",
            "total",
            "activity",
            "results",
            "warnings",
            "manifest",
            "error",
            "message",
            "download_url",
            "updated_at",
        }
        changes = {key: value for key, value in changes.items() if key in allowed}
        assignments = ", ".join(f"{key} = ?" for key in changes)
        with self._connect() as conn:
            # assignments 只来自上面的固定白名单，不包含任何用户可控 SQL 标识符。
            cursor = conn.execute(
                f"UPDATE tasks SET {assignments} WHERE task_id = ?",  # nosec B608
                (*changes.values(), task_id),
            )
        return cursor.rowcount == 1

    def delete(self, task_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))

    def touch_claim(self, task_id, worker_id):
        """Extend the lease of a running task while it reports progress."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET claimed_at = ?, updated_at = ? "
                "WHERE task_id = ? AND status = 'parsing' AND worker_id = ?",
                (now, now, task_id, worker_id),
            )

    def stale_ids(self, max_age):
        cutoff = time.time() - max_age
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id FROM tasks WHERE status NOT IN ('queued', 'parsing') AND updated_at < ?",
                (cutoff,),
            ).fetchall()
        return [row["task_id"] for row in rows]

    def claim_next(self, worker_id, stale_after=1800):
        """Atomically claim one queued job, reclaiming abandoned claims."""
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE tasks SET status = 'queued', worker_id = NULL, claimed_at = NULL "
                "WHERE status = 'parsing' AND claimed_at < ?",
                (now - stale_after,),
            )
            row = conn.execute(
                "SELECT task_id FROM tasks WHERE status = 'queued' ORDER BY updated_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE tasks SET status = 'parsing', worker_id = ?, claimed_at = ?, "
                "attempts = attempts + 1, updated_at = ? WHERE task_id = ?",
                (worker_id, now, now, row["task_id"]),
            )
            claimed = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (row["task_id"],)
            ).fetchone()
        return self._decode(claimed)

    def recover_interrupted(self):
        """Return jobs left in parsing state to the queue after a restart."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'queued', worker_id = NULL, claimed_at = NULL, "
                "error = 'Task requeued after worker restart', updated_at = ? "
                "WHERE status = 'parsing'",
                (time.time(),),
            )
