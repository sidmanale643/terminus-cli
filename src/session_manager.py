import json
import os
import sqlite3

from src.constants import DEFAULT_DATABASE_DIR


class SessionHistory:
    def __init__(self):
        os.makedirs(DEFAULT_DATABASE_DIR, exist_ok=True)

        db_path = os.path.join(DEFAULT_DATABASE_DIR, "chat_history.db")
        self.con = sqlite3.connect(db_path)
        self.ch_cursor = self.con.cursor()
        self._session_rows: list[dict] = []
        self._next_session_id = 1

        self._initialize_tables()

    def _initialize_tables(self) -> None:
        self.ch_cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.con.commit()

    @staticmethod
    def _encode_message(message: dict) -> str:
        return json.dumps(message, ensure_ascii=False, default=str)

    def insert_to_session_history(self, role, content):
        if not isinstance(content, str):
            content = self._encode_message(content)

        row = {
            "id": self._next_session_id,
            "role": role,
            "content": content,
        }
        self._next_session_id += 1
        self._session_rows.append(row)
        return row["id"]

    def record_message(self, message: dict):
        if not isinstance(message, dict):
            raise TypeError("session messages must be dictionaries")
        if "role" not in message:
            raise ValueError("session messages require a role")
        return self.insert_to_session_history(
            message["role"], self._encode_message(message)
        )

    def retrieve_session_history(self, limit=None):
        rows = self._session_rows
        if limit is not None:
            if limit <= 0:
                rows = []
            else:
                rows = list(reversed(rows[-limit:]))

        if limit is None:
            rows = list(rows)

        return [dict(row) for row in rows]

    def clear_session_history(self):
        self._session_rows.clear()
        self._next_session_id = 1

    def set_preference(self, key: str, value: str):
        self.ch_cursor.execute(
            "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.con.commit()

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        self.ch_cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = self.ch_cursor.fetchone()
        return row[0] if row else default

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
