"""SQLite persistence for mission audit and replay."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any

from src.constants import TERMINUS_DIR
from src.mission.models import (
    MissionEvent,
    MissionPhase,
    MissionStatus,
    MissionTask,
    TaskResult,
)


class MissionStore:
    def __init__(self, db_path: str | None = None):
        os.makedirs(TERMINUS_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(TERMINUS_DIR, "mission_control.db")
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    response_tokens INTEGER NOT NULL DEFAULT 0,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    repair_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL
                );

                CREATE TABLE IF NOT EXISTS mission_tasks (
                    mission_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    title TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    file_scope TEXT NOT NULL,
                    dependencies TEXT NOT NULL,
                    acceptance_criteria TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (mission_id, task_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(id)
                );

                CREATE TABLE IF NOT EXISTS mission_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL,
                    task_id TEXT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mission_events_mission
                    ON mission_events(mission_id, sequence);
                """
            )
            self._ensure_columns(
                "missions",
                {
                    "provider": "TEXT",
                    "model": "TEXT",
                    "prompt_tokens": "INTEGER NOT NULL DEFAULT 0",
                    "response_tokens": "INTEGER NOT NULL DEFAULT 0",
                },
            )

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {
            str(row[1])
            for row in self._connection.execute(f"PRAGMA table_info({table})")
        }
        for name, declaration in columns.items():
            if name not in existing:
                self._connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"
                )

    def create_mission(
        self,
        mission_id: str,
        goal: str,
        cwd: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        now = time.time()
        payload = {"goal": goal, "cwd": cwd, "phase": MissionPhase.BRIEF.value}
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model
        event = MissionEvent(
            mission_id=mission_id,
            event_type="mission_created",
            payload=payload,
            timestamp=now,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO missions
                    (id, goal, cwd, provider, model, phase, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    goal,
                    cwd,
                    provider,
                    model,
                    MissionPhase.BRIEF.value,
                    MissionStatus.RUNNING.value,
                    now,
                    now,
                ),
            )
            event.sequence = self._insert_event(event)

    def transition(
        self,
        mission_id: str,
        phase: MissionPhase,
        status: MissionStatus,
        summary: str | None = None,
        repair_count: int | None = None,
    ) -> MissionEvent:
        now = time.time()
        terminal = status not in {MissionStatus.RUNNING, MissionStatus.AWAITING_INPUT}
        payload: dict[str, Any] = {"phase": phase.value, "status": status.value}
        if summary is not None:
            payload["summary"] = summary
        event = MissionEvent(
            mission_id=mission_id,
            event_type="mission_transition",
            payload=payload,
            timestamp=now,
        )
        assignments = ["phase = ?", "status = ?", "updated_at = ?"]
        values: list[Any] = [phase.value, status.value, now]
        if summary is not None:
            assignments.append("summary = ?")
            values.append(summary)
        if repair_count is not None:
            assignments.append("repair_count = ?")
            values.append(repair_count)
        if terminal:
            assignments.append("completed_at = ?")
            values.append(now)
        values.append(mission_id)
        with self._lock, self._connection:
            self._connection.execute(
                f"UPDATE missions SET {', '.join(assignments)} WHERE id = ?", values
            )
            event.sequence = self._insert_event(event)
        return event

    def record_usage(
        self,
        mission_id: str,
        payload: dict[str, Any],
        task_id: str | None = None,
    ) -> MissionEvent:
        prompt_tokens = max(0, int(payload.get("prompt_tokens") or 0))
        response_tokens = max(0, int(payload.get("response_tokens") or 0))
        event = MissionEvent(
            mission_id=mission_id,
            event_type="llm_usage",
            payload={
                **payload,
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
            },
            task_id=task_id,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE missions
                SET prompt_tokens = prompt_tokens + ?,
                    response_tokens = response_tokens + ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (prompt_tokens, response_tokens, time.time(), mission_id),
            )
            event.sequence = self._insert_event(event)
        return event

    def add_task(self, mission_id: str, task: MissionTask) -> MissionEvent:
        now = time.time()
        event = MissionEvent(
            mission_id,
            "task_spawned",
            task.to_dict(),
            task.task_id,
            now,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO mission_tasks (
                    mission_id, task_id, role, title, instructions, file_scope,
                    dependencies, acceptance_criteria, attempt, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    task.task_id,
                    task.role.value,
                    task.title,
                    task.instructions,
                    json.dumps(task.file_scope),
                    json.dumps(task.dependencies),
                    json.dumps(task.acceptance_criteria),
                    task.attempt,
                    "queued",
                    now,
                    now,
                ),
            )
            event.sequence = self._insert_event(event)
        return event

    def update_task(self, mission_id: str, result: TaskResult) -> MissionEvent:
        now = time.time()
        event = MissionEvent(
            mission_id,
            "task_result",
            result.to_dict(),
            result.task_id,
            now,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE mission_tasks
                SET status = ?, result = ?, error = ?, updated_at = ?
                WHERE mission_id = ? AND task_id = ?
                """,
                (
                    result.status.value,
                    json.dumps(result.to_dict()),
                    result.error,
                    now,
                    mission_id,
                    result.task_id,
                ),
            )
            event.sequence = self._insert_event(event)
        return event

    def set_task_status(
        self, mission_id: str, task_id: str, status: str
    ) -> MissionEvent:
        event = MissionEvent(
            mission_id,
            "task_status",
            {"status": status},
            task_id,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE mission_tasks SET status = ?, updated_at = ?
                WHERE mission_id = ? AND task_id = ?""",
                (status, time.time(), mission_id, task_id),
            )
            event.sequence = self._insert_event(event)
        return event

    def append_event(self, event: MissionEvent) -> MissionEvent:
        with self._lock, self._connection:
            event.sequence = self._insert_event(event)
        return event

    def _insert_event(self, event: MissionEvent) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO mission_events (mission_id, task_id, event_type, payload, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.mission_id,
                event.task_id,
                event.event_type,
                json.dumps(event.payload),
                event.timestamp,
            ),
        )
        return int(cursor.lastrowid)

    def list_missions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, goal, cwd, provider, model, prompt_tokens,
                       response_tokens, phase, status, repair_count, summary,
                       created_at, updated_at, completed_at
                FROM missions ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM missions WHERE id = ?", (mission_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_events(self, mission_id: str) -> list[MissionEvent]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT sequence, mission_id, task_id, event_type, payload, timestamp
                FROM mission_events WHERE mission_id = ? ORDER BY sequence
                """,
                (mission_id,),
            ).fetchall()
        return [
            MissionEvent(
                sequence=row["sequence"],
                mission_id=row["mission_id"],
                task_id=row["task_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def mark_active_interrupted(self) -> int:
        rows = self.list_active_ids()
        for mission_id in rows:
            self.transition(
                mission_id,
                MissionPhase.TERMINAL,
                MissionStatus.INTERRUPTED,
                summary="Mission was interrupted before this Terminus process started.",
            )
        return len(rows)

    def list_active_ids(self) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id FROM missions WHERE status IN (?, ?)",
                (MissionStatus.RUNNING.value, MissionStatus.AWAITING_INPUT.value),
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
