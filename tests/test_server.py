"""Integration regressions for the shared app, with zero external API calls."""
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from unified.server import CatalogCache, ROOT, Settings, create_app
from unified.state import Workspace


class UnconfiguredFounders:
    configured = False


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'GARDEN_ACCESS_TOKEN': '', 'GARDEN_ENV_FILE': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def client(self, **kwargs):
        return TestClient(create_app(runtime_dir=self.runtime, settings=Settings(api_key=''),
                                    founder_reader=UnconfiguredFounders(), **kwargs),
                          base_url='http://127.0.0.1')

    def test_catalog_detail_and_shortlist_survive_restart(self):
        with self.client() as client:
            catalog = client.get('/api/catalog').json()
            self.assertGreater(len(catalog['companies']), 700)
            company = catalog['companies'][0]
            self.assertEqual(client.get('/api/companies/' + company['id']).json(), company)
            response = client.put('/api/shortlist/' + company['id'], json={'saved': True, 'note': 'Verify the relationship date.'})
            self.assertEqual(response.status_code, 200)
            self.assertIn(company['id'], response.json()['ids'])
            self.assertEqual(client.put('/api/shortlist/missing', json={'saved': True}).status_code, 404)
            self.assertEqual(client.put('/api/shortlist/company-0000000000000000', json={'saved': False, 'note': 'unbounded'}).status_code, 404)
        with self.client() as client:
            saved = client.get('/api/shortlist').json()
            self.assertIn(company['id'], saved['ids'])
            self.assertEqual(saved['notes'][company['id']], 'Verify the relationship date.')
            response = client.put('/api/shortlist/' + company['id'], json={'saved': False})
            self.assertNotIn(company['id'], response.json()['ids'])

    def test_saved_research_is_zero_call_and_idempotent(self):
        with self.client() as client, patch('reputation.providers.MonidSearch.search', side_effect=AssertionError('Unexpected live search')):
            data = {'count': 3, 'sector': 'All sectors', 'mode': 'sample', 'request_id': 'sample-regression-0001'}
            start = client.post('/api/research/jobs', json=data)
            self.assertEqual(start.status_code, 202, start.text)
            job_id = start.json()['id']
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = client.get('/api/research/jobs/' + job_id).json()
                if job['status'] in {'completed', 'partial', 'failed', 'interrupted'}:
                    break
                time.sleep(.02)
            self.assertIn(job['status'], {'completed', 'partial'}, job)
            self.assertGreater(len(job['cards']) + len(job['review_cards']), 0)
            self.assertEqual(job['metrics']['model_calls'], 0)
            self.assertEqual(job['metrics']['searches'], 0)
            again = client.post('/api/research/jobs', json=data)
            self.assertEqual(again.status_code, 200)
            self.assertEqual(again.json()['id'], job_id)
            conflict = client.post('/api/research/jobs', json={**data, 'count': 1})
            self.assertEqual(conflict.status_code, 409)
            companies = client.get('/api/catalog').json()['companies']
            self.assertEqual(sum(c['name'] == 'Queens Carbon' for c in companies), 1)

    def test_no_key_does_not_silently_return_sample(self):
        with self.client() as client:
            status = client.get('/api/research/status').json()
            self.assertFalse(status['live_available'])
            response = client.post('/api/research/jobs', json={
                'count': 1, 'mode': 'live', 'request_id': 'missing-key-regression-01'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['code'], 'missing_key')
            self.assertEqual(client.get('/api/research/jobs').json()['jobs'], [])
            self.assertEqual(client.post('/api/integrations/founders/sync', json={}).status_code, 503)

    def test_security_boundaries_and_strict_input(self):
        with self.client() as client:
            self.assertEqual(client.get('/api/catalog', headers={'Host': 'attacker.example'}).status_code, 403)
            data = {'count': 1, 'mode': 'sample', 'request_id': 'boundary-regression-0001'}
            self.assertEqual(client.post('/api/research/jobs', json=data, headers={'Origin': 'https://attacker.example'}).status_code, 403)
            self.assertEqual(client.post('/api/research/jobs', json=data, headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
            self.assertEqual(client.post('/api/research/jobs', content='{}').status_code, 415)
            self.assertEqual(client.post('/api/research/jobs', json={**data, 'count': True}).status_code, 422)
            self.assertEqual(client.post('/api/research/jobs', json={**data, 'count': 6}).status_code, 422)
            self.assertEqual(client.post('/api/research/jobs', json={**data, 'sector': 'unsupported'}).status_code, 422)
            self.assertEqual(client.post('/api/research/jobs', content='x' * 17000, headers={'Content-Type': 'application/json'}).status_code, 413)
            self.assertEqual(client.get('/api/research/jobs/../../etc/passwd').status_code, 404)

    def test_optional_access_token_protects_all_private_endpoints(self):
        with patch.dict('os.environ', {'GARDEN_ACCESS_TOKEN': 'test-secret-token'}), self.client() as client:
            self.assertTrue(client.get('/api/health').json()['auth_required'])
            for path in ['/api/catalog', '/api/shortlist', '/api/research/status', '/api/integrations']:
                self.assertEqual(client.get(path).status_code, 401)
                response = client.get(path, headers={'Authorization': 'Bearer test-secret-token'})
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('test-secret-token', response.text)
            self.assertIn("frame-ancestors 'none'", client.get('/api/health').headers['Content-Security-Policy'])

    def test_sector_mapping_changes_invalidate_cached_company_profiles(self):
        root = self.runtime / 'source'
        notes = root / 'business-and-market-potential/market-timing/sector-momentum-notes.md'
        notes.parent.mkdir(parents=True)
        (root / 'startups.csv').write_text('id,company,ceo_name,ceo_source_url,source_checked_on\nL1,Alpha,Alex,https://example.com/team,2026-09-25\n')
        notes.write_text('## Sector grouping\n\n| Sector | Companies |\n| --- | --- |\n| First | Alpha |\n')
        service = SimpleNamespace(store=SimpleNamespace(recent=lambda limit: []))
        cache = CatalogCache(root, service, Workspace(self.runtime / 'test.sqlite3'))
        self.assertEqual(cache.get()['companies'][0]['sector'], 'First')
        notes.write_text('## Sector grouping\n\n| Sector | Companies |\n| --- | --- |\n| Second | Alpha |\n')
        self.assertEqual(cache.get()['companies'][0]['sector'], 'Second')

    def test_founder_import_diagnostics_are_visible_and_failed_refresh_preserves_cache(self):
        class Reader:
            configured = True
            last_limitations = ('1 orphan record was omitted.',)
            fail = False

            def fetch_profiles(self):
                if self.fail:
                    raise RuntimeError('private provider failure')
                return {}

        reader = Reader()
        app = create_app(runtime_dir=self.runtime, settings=Settings(api_key=''), founder_reader=reader)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            response = client.post('/api/integrations/founders/sync', json={})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['warnings'], list(reader.last_limitations))
            before = client.get('/api/integrations').json()
            self.assertEqual(before['founders_limitations'], list(reader.last_limitations))
            self.assertIn('Founder import: 1 orphan record was omitted.', client.get('/api/catalog').json()['notices'])
            reader.fail = True
            failure = client.post('/api/integrations/founders/sync', json={})
            self.assertEqual(failure.status_code, 502)
            self.assertNotIn('private provider', failure.text)
            self.assertEqual(client.get('/api/integrations').json()['founders_last_synced'], before['founders_last_synced'])


if __name__ == '__main__':
    unittest.main()
