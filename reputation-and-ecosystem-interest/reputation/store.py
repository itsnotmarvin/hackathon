import json
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created REAL, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, observed REAL, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS request_ids (request_id TEXT PRIMARY KEY, job_id TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save_job(self, job):
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (job['id'], job['created_epoch'], json.dumps(job)))
            if job.get('request_id'):
                db.execute('INSERT OR IGNORE INTO request_ids VALUES (?, ?)', (job['request_id'], job['id']))

    def remember_request(self, request_id, job_id):
        if request_id:
            with self.connect() as db:
                db.execute('INSERT OR IGNORE INTO request_ids VALUES (?, ?)', (request_id, job_id))

    def job_for_request(self, request_id):
        with self.connect() as db:
            row = db.execute('SELECT jobs.data FROM request_ids JOIN jobs ON jobs.id=request_ids.job_id '
                             'WHERE request_id=?', (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self, limit=10):
        with self.connect() as db:
            rows = db.execute('SELECT data FROM jobs ORDER BY created DESC LIMIT ?', (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def recover(self):
        with self.connect() as db:
            rows = db.execute('SELECT data FROM jobs').fetchall()
        for row in rows:
            job = json.loads(row[0])
            if job['status'] in ('queued', 'running'):
                job.update(status='interrupted', stage='Research interrupted',
                           error='The backend restarted. Start a new run to reuse cached pages and retain these saved findings.')
                self.save_job(job)

    def cache_page(self, page):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO pages VALUES (?, ?, ?)',
                       (page['url'], time.time(), json.dumps(page)))

    def cached_page(self, url, ttl):
        with self.connect() as db:
            row = db.execute('SELECT observed, data FROM pages WHERE url=?', (url,)).fetchone()
        return json.loads(row[1]) if row and time.time() - row[0] < ttl else None
