"""Small, local, transactional store for user work and imported profiles."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Workspace:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS shortlist '
                       '(company_id TEXT PRIMARY KEY, saved INTEGER NOT NULL, note TEXT NOT NULL, updated TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def shortlist(self):
        with self.connect() as db:
            rows = db.execute('SELECT company_id,saved,note FROM shortlist ORDER BY updated DESC,company_id').fetchall()
        return {'ids': [r[0] for r in rows if r[1]], 'notes': {r[0]: r[2] for r in rows if r[2]}}

    def update_shortlist(self, company_id, saved, note=None):
        with self.connect() as db:
            prior = db.execute('SELECT note FROM shortlist WHERE company_id=?', (company_id,)).fetchone()
            retained_note = note if note is not None else (prior[0] if prior else '')
            if not saved and not retained_note:
                db.execute('DELETE FROM shortlist WHERE company_id=?', (company_id,))
            else:
                db.execute('INSERT INTO shortlist VALUES (?,?,?,?) ON CONFLICT(company_id) DO UPDATE '
                           'SET saved=excluded.saved,note=excluded.note,updated=excluded.updated',
                           (company_id, int(saved), retained_note, now()))
        return self.shortlist()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.connect() as db:
            db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key, json.dumps(value)))
