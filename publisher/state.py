import json
import sqlite3
from pathlib import Path
from .common import encode


class State:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def get(self, key):
        row = self.db.execute("SELECT value FROM records WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else {}

    def set(self, key, value):
        self.db.execute("INSERT INTO records VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, encode(value).decode()))
        self.db.commit()

    def close(self):
        self.db.close()
