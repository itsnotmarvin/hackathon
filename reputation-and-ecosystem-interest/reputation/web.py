"""Mountable WSGI adapter for the shared site's reputation module."""
import hmac
import json
import re
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

from .config import ROOT, Settings
from .engine import BusyError, PIPELINE_VERSION, ResearchService
from .providers import ProviderError
from .schemas import SECTORS
from .store import Store


class Application:
    def __init__(self, settings=None, service=None):
        self.settings = settings or Settings.from_env()
        self.service = service or ResearchService(self.settings, Store(self.settings.db_path))

    def __call__(self, env, respond):
        path, method = env.get('PATH_INFO', '/'), env.get('REQUEST_METHOD', 'GET')
        headers = [('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
                   ('Cache-Control', 'no-store'),
                   ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]

        def send(code, value, content_type='application/json; charset=utf-8'):
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            respond(f'{code} {HTTPStatus(code).phrase}', headers + [('Content-Type', content_type),
                                                                   ('Content-Length', str(len(data)))])
            return [data]

        host = env.get('HTTP_HOST', '')
        try:
            hostname = urlsplit('http://' + host).hostname
        except ValueError:
            hostname = None
        # A local preview cannot be used through DNS rebinding or arbitrary Host headers.
        if not self.settings.access_token and hostname not in ('localhost', '127.0.0.1', '::1'):
            return send(403, {'error': 'This preview only accepts local requests.'})
        if path.startswith('/api/reputation'):
            if path != '/api/reputation/status' and self.settings.access_token:
                authorization = env.get('HTTP_AUTHORIZATION', '')
                if not hmac.compare_digest(authorization.encode(), ('Bearer ' + self.settings.access_token).encode()):
                    return send(401, {'error': 'Enter the server access token to use this preview.'})
            if method == 'GET' and path == '/api/reputation/status':
                return send(200, {**self.settings.public_status(), 'sectors': SECTORS,
                                  'limits': {'max_results': 5, 'research_minutes': self.settings.max_seconds // 60}})
            if method == 'GET' and path == '/api/reputation/jobs':
                return send(200, {'jobs': [{k: j.get(k) for k in ('id', 'created_at', 'status', 'mode', 'qualified_count', 'sector')}
                                           for j in self.service.store.recent()]})
            if method == 'GET' and re.fullmatch(r'/api/reputation/jobs/[a-f0-9]{32}', path):
                job = self.service.store.get_job(path.rsplit('/', 1)[-1])
                if job and job.get('pipeline_version') != PIPELINE_VERSION:
                    job['warnings'].append('This saved run used an earlier assessment version. Start new research to apply the current checks.')
                return send(200, job) if job else send(404, {'error': 'Research run not found.'})
            if method == 'POST' and path == '/api/reputation/jobs':
                origin = env.get('HTTP_ORIGIN')
                if origin and origin != env.get('wsgi.url_scheme', 'http') + '://' + host:
                    return send(403, {'error': 'Requests must come from this website.'})
                if env.get('HTTP_SEC_FETCH_SITE') == 'cross-site':
                    return send(403, {'error': 'Cross-site requests are not accepted.'})
                if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
                    return send(415, {'error': 'Use application/json.'})
                try:
                    length = int(env.get('CONTENT_LENGTH', '0'))
                    if not 0 < length <= 4096:
                        return send(413, {'error': 'Invalid request size.'})
                    data = json.loads(env['wsgi.input'].read(length))
                    if not isinstance(data, dict):
                        raise ValueError()
                    count, sector, mode = data.get('count', 3), data.get('sector', 'All sectors'), data.get('mode', 'live')
                    request_id = data.get('request_id')
                    if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', request_id)):
                        raise ValueError()
                    if (type(count) is not int or not 1 <= count <= 5 or sector not in ['All sectors', *SECTORS]
                            or mode not in ('live', 'sample')):
                        raise ValueError()
                except (ValueError, TypeError, UnicodeError):
                    return send(400, {'error': 'Choose 1–5 companies and a supported sector and research mode.'})
                try:
                    job, reused = self.service.start(count=count, sector=sector, mode=mode, request_id=request_id)
                    return send(200 if reused else 202, {'id': job['id'], 'reused': reused})
                except BusyError as exc:
                    return send(409, {'error': 'A research run is already active.', 'id': exc.job_id})
                except ProviderError as exc:
                    code = {'job_limit': 429, 'request_conflict': 409}.get(exc.code, 503)
                    return send(code, {'error': str(exc), 'code': exc.code})
            return send(404, {'error': 'Endpoint not found.'})
        static = {'/': ('index.html', 'text/html'), '/reputation': ('index.html', 'text/html'),
                  '/reputation/': ('index.html', 'text/html'), '/reputation/app.js': ('app.js', 'text/javascript'),
                  '/reputation/demo.json': ('demo.json', 'application/json'),
                  '/reputation/style.css': ('style.css', 'text/css'), '/favicon.ico': (None, None)}
        if method != 'GET' or path not in static:
            return send(404, {'error': 'Page not found.'})
        name, content_type = static[path]
        if name is None:
            return send(204, b'')
        return send(200, (ROOT / 'web' / name).read_bytes(), content_type + '; charset=utf-8')


def create_app(settings=None, service=None):
    return Application(settings, service)
