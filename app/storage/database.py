import sqlite3
import uuid
import json
import os
from datetime import datetime, timezone
from app.config import settings

DB_PATH = os.path.join(settings.data_dir, "morphsheet.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversion_tasks (
    task_id         TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_file_path TEXT,
    target_format   TEXT NOT NULL,
    instructions    TEXT,
    skill_id        TEXT,
    status          TEXT NOT NULL DEFAULT 'in_progress',
    source_schema   TEXT,
    target_schema   TEXT,
    execution_code  TEXT,
    error_message   TEXT,
    token_used      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS skill_templates (
    skill_id       TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT,
    source_schema  TEXT NOT NULL,
    target_spec    TEXT NOT NULL,
    code           TEXT NOT NULL,
    column_mapping TEXT,
    usage_count    INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_created ON conversion_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_skills_usage ON skill_templates(usage_count DESC);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(settings.data_dir, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)


# ---- Tasks ----

def create_task(source_filename: str, target_format: str,
                instructions: str, source_file_path: str = "") -> str:
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO conversion_tasks
               (task_id, source_filename, source_file_path, target_format,
                instructions, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'in_progress', ?)""",
            (task_id, source_filename, source_file_path, target_format,
             instructions, now))
    return task_id


def update_task(task_id: str, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [task_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE conversion_tasks SET {sets} WHERE task_id = ?", values)


def complete_task(task_id: str, status: str = "completed",
                  execution_code: str = "", token_used: int = 0):
    now = datetime.now(timezone.utc).isoformat()
    update_task(task_id, status=status, completed_at=now,
                execution_code=execution_code, token_used=token_used)


def get_history(limit: int = 20, offset: int = 0) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversion_tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
    return [dict(r) for r in rows]


def get_task(task_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversion_tasks WHERE task_id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


# ---- Skills ----

def save_skill(name: str, description: str, source_schema: dict,
               target_spec: dict, code: str, column_mapping: dict) -> str:
    skill_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO skill_templates
               (skill_id, name, description, source_schema, target_spec,
                code, column_mapping, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (skill_id, name, description,
             json.dumps(source_schema, ensure_ascii=False),
             json.dumps(target_spec, ensure_ascii=False),
             code, json.dumps(column_mapping, ensure_ascii=False),
             now, now))
    return skill_id


def get_skills(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_templates ORDER BY usage_count DESC, created_at DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_skill(skill_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM skill_templates WHERE skill_id = ?", (skill_id,)).fetchone()
    return dict(row) if row else None


def increment_skill_usage(skill_id: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE skill_templates SET usage_count = usage_count + 1, updated_at = ? WHERE skill_id = ?",
            (now, skill_id))


def delete_skill(skill_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM skill_templates WHERE skill_id = ?", (skill_id,))


# Initialize DB on import
init_db()
