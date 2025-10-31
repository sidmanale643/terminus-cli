import sqlite3
import datetime
import os
import json
from src.constants import DEFAULT_DATABASE_DIR

class SessionHistory:
    def __init__(self):
        if not os.path.exists(DEFAULT_DATABASE_DIR):
            os.makedirs(DEFAULT_DATABASE_DIR)
        
        db_path = os.path.join(DEFAULT_DATABASE_DIR, "chat_history.db")
        self.con = sqlite3.connect(db_path)
        self.ch_cursor = self.con.cursor()
        
        self.session_history = sqlite3.connect(":memory:")
        self.sh_cursor = self.session_history.cursor()
        
        self._initialize_tables()

    def _initialize_tables(self):
        try:
            self.ch_cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    chat_history TEXT NOT NULL
                )
            """)
            self.con.commit()
            
            self.sh_cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            self.session_history.commit()
            
        except sqlite3.OperationalError as e:
            print(f"Error initializing tables: {e}")

    @staticmethod
    def _get_timestamp():
        return datetime.datetime.now().isoformat()

    def insert_to_chat_history(self, name, chat_history):
        timestamp = self._get_timestamp()
        chat_history_json = json.dumps(chat_history)
        
        self.ch_cursor.execute(
            "INSERT INTO chat_history (name, timestamp, chat_history) VALUES (?, ?, ?)",
            (name, timestamp, chat_history_json)
        )
        self.con.commit()
        return self.ch_cursor.lastrowid

    def insert_to_session_history(self, role, content):
        timestamp = self._get_timestamp()
        
        self.sh_cursor.execute(
            "INSERT INTO session_history (timestamp, role, content) VALUES (?, ?, ?)",
            (timestamp, role, content)
        )
        self.session_history.commit()
        return self.sh_cursor.lastrowid

    def retrieve_chat_history(self, name=None, chat_id=None, limit=None):
        query = "SELECT id, name, timestamp, chat_history FROM chat_history"
        params = []
        
        if chat_id:
            query += " WHERE id = ?"
            params.append(chat_id)
        elif name:
            query += " WHERE name = ?"
            params.append(name)
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        self.ch_cursor.execute(query, params)
        results = self.ch_cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "name": row[1],
                "timestamp": row[2],
                "chat_history": json.loads(row[3])
            }
            for row in results
        ]

    def retrieve_session_history(self, limit=None):
        query = "SELECT id, timestamp, role, content FROM session_history ORDER BY id"
        
        if limit:
            query += " DESC LIMIT ?"
            self.sh_cursor.execute(query, (limit,))
        else:
            self.sh_cursor.execute(query)
        
        results = self.sh_cursor.fetchall()
        
        return [
            {
                "id": row[0],
                "timestamp": row[1],
                "role": row[2],
                "content": row[3]
            }
            for row in results
        ]

    def save_session_to_chat_history(self, name):
        session_messages = self.retrieve_session_history()
        chat_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in session_messages
        ]
        return self.insert_to_chat_history(name, chat_history)

    def clear_session_history(self):
        self.sh_cursor.execute("DELETE FROM session_history")
        self.session_history.commit()

    def delete_chat_history(self, chat_id):
        self.ch_cursor.execute("DELETE FROM chat_history WHERE id = ?", (chat_id,))
        self.con.commit()

    def close(self):
        self.con.close()
        self.session_history.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()