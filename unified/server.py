"""Single-process FastAPI host for the four shared research pillars."""
from contextlib import asynccontextmanager
from dataclasses import replace
import hmac
import os
from pathlib import Path
import re
import sys
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from starlette.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .catalog import build_catalog
from .founders import FounderReader
from .state import Workspace, now

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'reputation-and-ecosystem-interest'))
from reputation.config import Settings, load_env  # noqa: E402
from reputation.engine import BusyError, PIPELINE_VERSION, ResearchService  # noqa: E402
from reputation.providers import ProviderError  # noqa: E402
from reputation.schemas import SECTORS  # noqa: E402
from reputation.store import Store  # noqa: E402


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    count: StrictInt = Field(default=3, ge=1, le=5)
    sector: str = Field(default='All sectors', max_length=100)
    mode: Literal['live', 'sample'] = 'live'
    request_id: str = Field(pattern=r'^[A-Za-z0-9-]{16,64}$')


class ShortlistRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    saved: StrictBool
    note: str | None = Field(default=None, max_length=4000)


class CatalogCache:
    def __init__(self, root, service, workspace):
        self.root, self.service, self.workspace = root, service, workspace
        self.lock = threading.Lock()
        self.signature = None
        self.value = None

    def get(self):
        with self.lock:
            jobs = self.service.store.recent(10000)
            founders = self.workspace.get('founder_profiles', {})
            inputs = [self.root / 'startups.csv',
                      self.root / 'reputation-and-ecosystem-interest/web/demo.json',
                      self.root / 'business-and-market-potential/market-timing/sector-momentum-notes.md',
                      *sorted((self.root / 'business-and-market-potential').rglob('*.csv'))]
            signature = (tuple((j['id'], j.get('updated_at'), j.get('status')) for j in jobs),
                         founders.get('synced_at'), tuple((str(p), p.stat().st_mtime_ns) for p in inputs if p.exists()))
            if self.value is None or self.signature != signature:
                self.value = build_catalog(self.root, jobs=jobs, founder_profiles=founders.get('profiles', {}))
                for limitation in founders.get('limitations', []):
                    notice = 'Founder import: ' + limitation
                    if notice not in self.value['notices']:
                        self.value['notices'].append(notice)
                self.signature = signature
            return self.value


def create_app(*, root=ROOT, runtime_dir=None, settings=None, service=None, founder_reader=None):
    root = Path(root)
    runtime = Path(runtime_dir or os.environ.get('GARDEN_RUNTIME_DIR', root / '.runtime'))
    if os.environ.get('GARDEN_ENV_FILE'):
        # Only the reputation module's explicit configuration allowlist is loaded.
        load_env(Path(os.environ['GARDEN_ENV_FILE']).expanduser())
    settings = settings or Settings.from_env()
    settings = replace(settings, db_path=runtime / 'reputation.sqlite3')
    access_token = os.environ.get('GARDEN_ACCESS_TOKEN') or settings.access_token

    @asynccontextmanager
    async def lifespan(app):
        runtime.mkdir(parents=True, exist_ok=True)
        lock_file = None
        if service is None:
            # ResearchService coordination is process-local. Prevent a second host
            # from recovering or racing active jobs in the same runtime directory.
            lock_file = (runtime / 'server.lock').open('a')
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock_file.close()
                raise RuntimeError('Garden State is already running with this runtime directory. Use one server process.') from None
        app.state.workspace = Workspace(runtime / 'workspace.sqlite3')
        app.state.research = service or ResearchService(settings, Store(settings.db_path))
        app.state.founders = founder_reader or FounderReader()
        app.state.sync_lock = threading.Lock()
        app.state.catalog = CatalogCache(root, app.state.research, app.state.workspace)
        try:
            yield
        finally:
            if service is None:
                app.state.research.close()
            close_founders = getattr(app.state.founders, 'close', None)
            if callable(close_founders):
                close_founders()
            if lock_file:
                lock_file.close()

    app = FastAPI(title='Garden State — Startup intelligence', version='1.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware('http')
    async def guard(request, call_next):
        error = None
        if not access_token and request.url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            error = JSONResponse({'error': 'This workspace accepts local connections only.'}, status_code=403)
        if error is None and request.url.path.startswith('/api/') and request.url.path != '/api/health' and access_token:
            supplied = request.headers.get('authorization', '')
            if not hmac.compare_digest(supplied.encode(), ('Bearer ' + access_token).encode()):
                error = JSONResponse({'error': 'Enter the workspace access token to continue.'}, status_code=401)
        if error is None and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('origin')
            expected = str(request.base_url).rstrip('/')
            if (origin and origin != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
                error = JSONResponse({'error': 'Requests must come from this workspace.'}, status_code=403)
            elif request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                error = JSONResponse({'error': 'Use application/json.'}, status_code=415)
            else:
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 16384:
                        error = JSONResponse({'error': 'Request is too large.'}, status_code=413)
                        break
                    chunks.append(chunk)
                if error is None:
                    request._body = b''.join(chunks)
        response = error if error is not None else await call_next(request)
        response.headers.update({
            'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
            'X-Frame-Options': 'DENY', 'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'error': 'Check the submitted values and try again.'}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({'error': exc.detail}, status_code=exc.status_code)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'auth_required': bool(access_token), 'version': '1.0.0'}

    @app.get('/api/catalog')
    def catalog():
        return app.state.catalog.get()

    def find_company(company_id):
        company = next((c for c in app.state.catalog.get()['companies'] if c['id'] == company_id), None)
        if not company:
            raise HTTPException(404, 'Company not found.')
        return company

    @app.get('/api/companies/{company_id}')
    def company(company_id: str):
        return find_company(company_id)

    @app.get('/api/shortlist')
    def shortlist():
        return app.state.workspace.shortlist()

    @app.put('/api/shortlist/{company_id}')
    def update_shortlist(company_id: str, data: ShortlistRequest):
        # A stale saved ID can still be removed after a source record disappears.
        if not re.fullmatch(r'company-[a-f0-9]{16,64}', company_id):
            raise HTTPException(404, 'Company not found.')
        if data.saved:
            find_company(company_id)
        elif not any(c['id'] == company_id for c in app.state.catalog.get()['companies']):
            existing = app.state.workspace.shortlist()
            if company_id not in existing['ids'] and company_id not in existing['notes']:
                raise HTTPException(404, 'Company not found.')
        return app.state.workspace.update_shortlist(company_id, data.saved, data.note)

    @app.get('/api/research/status')
    def research_status():
        public = settings.public_status()
        ready = public['gemini_configured'] and public['search_configured']
        return {**public, 'live_available': ready, 'sectors': ['All sectors', *SECTORS],
                'message': 'Live research is configured. Provider availability is checked during each run.' if ready
                else 'Saved public research is ready. Live research needs the server Gemini key and Monid search setup.',
                'limits': {'max_results': 5, 'research_minutes': settings.max_seconds // 60}}

    @app.get('/api/research/jobs')
    def research_jobs():
        fields = ('id', 'created_at', 'updated_at', 'status', 'stage', 'mode', 'qualified_count', 'sector', 'error')
        return {'jobs': [{k: j.get(k) for k in fields} for j in app.state.research.store.recent(30)]}

    @app.get('/api/research/jobs/{job_id}')
    def research_job(job_id: str):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise HTTPException(404, 'Research run not found.')
        job = app.state.research.store.get_job(job_id)
        if not job:
            raise HTTPException(404, 'Research run not found.')
        if job.get('pipeline_version') != PIPELINE_VERSION:
            warning = 'This saved run used an earlier assessment version. Start new research to apply current checks.'
            job.setdefault('warnings', [])
            if warning not in job['warnings']:
                job['warnings'].append(warning)
        return job

    @app.post('/api/research/jobs')
    def start_research(data: ResearchRequest):
        if data.sector not in ['All sectors', *SECTORS]:
            raise HTTPException(422, 'Choose a supported research sector.')
        try:
            job, reused = app.state.research.start(**data.model_dump())
        except BusyError as exc:
            return JSONResponse({'error': 'Research is already running.', 'id': exc.job_id}, status_code=409)
        except ProviderError as exc:
            return JSONResponse({'error': str(exc), 'code': exc.code},
                                status_code={'job_limit': 429, 'request_conflict': 409}.get(exc.code, 503))
        return JSONResponse({'id': job['id'], 'reused': reused}, status_code=200 if reused else 202)

    @app.get('/api/integrations')
    def integrations():
        saved = app.state.workspace.get('founder_profiles', {})
        configured = app.state.founders.configured
        limitations = saved.get('limitations', [])
        founder_message = ('Read-only database refresh is available.' if configured else
                           'Source-linked CEO records are available. Connect the team database for deeper profiles.')
        if limitations:
            founder_message += f' The last import has {len(limitations)} data-quality notes; see catalog notices.'
        return {'founders_configured': configured, 'founders_last_synced': saved.get('synced_at'),
                'founders_limitations': limitations, 'modules': [
            {'id': 'founders', 'name': 'Founders & leadership', 'status': 'connected' if configured else 'saved',
             'message': founder_message},
            {'id': 'business', 'name': 'Business & market', 'status': 'connected',
             'message': 'Team business assessments, headcount observations, and sector research.'},
            {'id': 'funding', 'name': 'Funding & financial health', 'status': 'partial',
             'message': 'SEC Form D filings provide fundraising evidence. Revenue, runway, and profitability remain unknown.'},
            {'id': 'reputation', 'name': 'Reputation & ecosystem', 'status': 'connected' if research_status()['live_available'] else 'saved',
             'message': 'Saved, sourced institutional research plus the existing live discovery service.'},
        ]}

    @app.post('/api/integrations/founders/sync')
    def sync_founders():
        if not app.state.founders.configured:
            raise HTTPException(503, 'The team database is not configured. Existing company evidence remains available.')
        if not app.state.sync_lock.acquire(blocking=False):
            raise HTTPException(409, 'A founder profile refresh is already running.')
        try:
            try:
                profiles = app.state.founders.fetch_profiles()
            except Exception:
                raise HTTPException(502, 'The founder database could not be read. Previously saved profiles were preserved.') from None
            timestamp = now()
            limitations = list(getattr(app.state.founders, 'last_limitations', ()))
            app.state.workspace.put('founder_profiles', {'profiles': profiles, 'synced_at': timestamp, 'limitations': limitations})
            return {'companies': len(profiles), 'synced_at': timestamp,
                    'warnings': limitations,
                    'message': 'Saved founder profiles refreshed. Name-based findings still require identity review.'
                    + (f' {len(limitations)} data-quality notes are available in catalog notices.' if limitations else '')}
        finally:
            app.state.sync_lock.release()

    static = root / 'unified/static'
    if static.exists():
        app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def home():
        return FileResponse(static / 'index.html')

    @app.get('/favicon.ico')
    def favicon():
        return Response(status_code=204)

    return app
