"""Failure-oriented checks. Example Company and all .example pages are test fixtures."""
import copy
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from reputation.config import Settings
from reputation.engine import BusyError, ResearchService
from reputation.evidence import assess, check_candidates, make_page, merge_assessments, rank_card, source_family, supported_event_date, verify_quote
from reputation.providers import Gemini, MonidSearch, ProviderError, public_url, schema_matches
from reputation.store import Store
from reputation.web import create_app

TODAY = date.today().isoformat()
CANDIDATE = {'name': 'Example Company', 'aliases': [], 'sector': 'Climate & materials'}
TEXT1 = f'Example Company is headquartered in Newark, New Jersey. In {TODAY}, Example Company licensed a technology from Example University.'
TEXT2 = f'Example Company and Example Industry began a joint research collaboration on {TODAY}.'


def pages():
    rows = [make_page({'url': 'https://university.example/news', 'text': TEXT1, 'published_date': TODAY}),
            make_page({'url': 'https://industry.example/news', 'text': TEXT2, 'published_date': TODAY})]
    return {p['id']: p for p in rows}


def record():
    p = list(pages().values())
    return {'name': CANDIDATE['name'], 'official_domain': '', 'sector': CANDIDATE['sector'],
            'description': 'Test fixture, not a real company.',
            'nj_presence': {'status': 'headquarters', 'location': 'Newark',
                            'evidence': [{'source_id': p[0]['id'], 'quote': TEXT1}]},
            'signals': [{'type': kind, 'organization': org, 'statement': text,
                         'event_date': TODAY, 'event_key': org, 'status': 'current',
                         'source_role': 'institution_confirmation', 'source_id': page['id'], 'quote': text}
                        for kind, org, text, page in [('technology_license', 'Example University', TEXT1, p[0]),
                                                       ('research_collaboration', 'Example Industry', TEXT2, p[1])]],
            'uncertainties': [], 'follow_up_query': ''}


class EvidenceTests(unittest.TestCase):
    def test_invented_quote_and_unknown_source_rejected(self):
        p = list(pages().values())[0]
        self.assertIsNone(verify_quote({'source_id': p['id'], 'quote': 'This quote does not exist.'}, pages()))
        self.assertIsNone(verify_quote({'source_id': 'fake', 'quote': TEXT1}, pages()))
        e = verify_quote({'source_id': p['id'], 'quote': TEXT1}, pages())
        self.assertEqual(p['text'][e['start_offset']:e['end_offset']], TEXT1)

    def test_different_company_cannot_inherit_signal_from_directory(self):
        p = pages(); r = record(); signal = r['signals'][0]
        foreign = 'Different Company won an industry award in New Jersey.'
        p[signal['source_id']]['text'] += '\n' + foreign
        signal['quote'] = foreign
        r['signals'] = [signal]
        self.assertEqual(assess(CANDIDATE, r, p)['signals'], [])

    def test_nj_quote_must_name_company(self):
        p = pages(); r = record(); e = r['nj_presence']['evidence'][0]
        p[e['source_id']]['text'] += ' Another Venture is based in Newark, NJ.'
        e['quote'] = 'Another Venture is based in Newark, NJ.'
        self.assertEqual(assess(CANDIDATE, r, p)['nj_presence']['status'], 'unclear')

    def test_identity_mismatch_rejected(self):
        r = record(); r['name'] = 'Someone Else'
        with self.assertRaises(ValueError): assess(CANDIDATE, r, pages())

    def test_unsupported_future_date_removed(self):
        r = record(); r['signals'][0]['event_date'] = '2099-01-01'
        c = assess(CANDIDATE, r, pages())
        self.assertIsNone(c['signals'][0]['event_date'])
        self.assertTrue(any('date was removed' in w for w in c['limitations']))

    def test_duplicate_announcements_do_not_create_new_events(self):
        r = record(); r['signals'].append(copy.deepcopy(r['signals'][0]))
        self.assertEqual(len(assess(CANDIDATE, r, pages())['signals']), 2)
        self.assertEqual(source_family('https://hax.co/a'), source_family('https://sosv.com/b'))
        self.assertEqual(source_family('https://njeda.gov/a'), source_family('https://njcsit.gov/b'))

    def test_unknown_and_proposed_work_is_not_substantial(self):
        r = record(); r['signals'][0]['status'] = 'unknown'; r['signals'][1]['status'] = 'announced'
        c = assess(CANDIDATE, r, pages())
        self.assertEqual(c['evidence_summary']['substantial_relationships'], 0)
        self.assertEqual(c['assessment'], 'limited_evidence')

    def test_multiple_pages_one_source_family_cannot_qualify(self):
        c = assess(CANDIDATE, record(), pages())
        c['signals'][1]['evidence'][0]['source_family'] = c['signals'][0]['evidence'][0]['source_family']
        rank_card(c)
        self.assertFalse(c['qualified'])

    def test_ecosystem_membership_is_not_nj_operations(self):
        r = record(); r['nj_presence']['status'] = 'ecosystem_only'
        c = assess(CANDIDATE, r, pages())
        self.assertFalse(c['qualified']); self.assertEqual(c['assessment'], 'location_review')

    def test_missing_dates_cannot_prove_recent_momentum(self):
        r = record(); p = pages()
        for s in r['signals']: s['event_date'] = ''
        for v in p.values(): v['published_at'] = None
        self.assertFalse(assess(CANDIDATE, r, p)['qualified'])

    def test_legal_suffix_does_not_hide_matching_company_pages(self):
        p = make_page({'url': 'https://test.example', 'text': 'Example Company, Inc. is a Newark-based startup with a university partnership.'})
        candidate = check_candidates({'candidates': [{'name': 'Example Company, Inc.', 'aliases': [], 'sector': 'Other', 'source_id': p['id'], 'quote': p['text']}]}, {p['id']: p}, 1)[0]
        self.assertIn('Example Company', candidate['aliases'])

    def test_cdn_ip_redirect_preserves_institution_source_family(self):
        p = make_page({'url': 'https://www.njcsit.gov/report.pdf', 'final_url': 'https://141.193.213.11/report.pdf', 'text': TEXT1})
        self.assertEqual(p['source_family'], 'njeda-csit'); self.assertEqual(p['url'], 'https://www.njcsit.gov/report.pdf')

    def test_access_challenge_is_not_counted_as_source_evidence(self):
        self.assertIsNone(make_page({'url': 'https://test.example', 'title': 'Checking your browser', 'text': 'Verify you are a human. ' * 5}))

    def test_city_listing_does_not_establish_headquarters(self):
        r = record(); p = pages(); e = r['nj_presence']['evidence'][0]
        e['quote'] = 'Example Company (Newark)'; p[e['source_id']]['text'] += '\n' + e['quote']
        self.assertEqual(assess(CANDIDATE, r, p)['nj_presence']['status'], 'operations')

    def test_proposed_research_cannot_get_actual_collaboration_credit(self):
        r = record(); p = pages(); s = r['signals'][1]
        s['quote'] = 'Example Company in collaboration with Example Industry proposes a research project.'
        p[s['source_id']]['text'] += '\n' + s['quote']
        c = assess(CANDIDATE, r, p)
        self.assertEqual(c['signals'][1]['status'], 'announced')
        self.assertEqual(c['evidence_summary']['substantial_relationships'], 1)

    def test_followup_retains_prior_evidence_but_new_status_takes_precedence(self):
        before = assess(CANDIDATE, record(), pages()); r = record()
        r['signals'] = r['signals'][1:]; r['signals'][0]['status'] = 'announced'
        after = merge_assessments(before, assess(CANDIDATE, r, pages()))
        self.assertEqual(len(after['signals']), 2)
        self.assertEqual(after['signals'][0]['status'], 'announced')
        self.assertEqual(after['evidence_summary']['substantial_relationships'], 1)

    def test_proposal_does_not_establish_investment(self):
        r = record(); p = pages(); s = r['signals'][1]; s['type'] = 'investor_affiliation'
        s['quote'] = 'Example Company proposes to develop a new technology for NASA.'
        p[s['source_id']]['text'] += '\n' + s['quote']
        c = assess(CANDIDATE, r, p)
        self.assertEqual(len(c['signals']), 1)
        self.assertTrue(any('investment relationship' in w for w in c['limitations']))

    def test_date_precision_cannot_exceed_quote(self):
        self.assertEqual(supported_event_date('2025-04-05', 'Example Company won in 2025.'), '2025')
        self.assertEqual(supported_event_date('2025-04-05', 'Example Company won on April 5, 2025.'), '2025-04-05')
        self.assertEqual(supported_event_date('2025-04-05', 'Example Company won in April 2025.'), '2025-04')


class ProviderTests(unittest.TestCase):
    @staticmethod
    def response(value):
        return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {
            'parts': [{'text': json.dumps(value)}]}}]}).encode())

    def test_transient_failures_recover_and_invalid_output_is_retried(self):
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']}
        failures = [
            [HTTPError('https://example.com', 503, 'busy', {}, io.BytesIO()),
             HTTPError('https://example.com', 503, 'busy', {}, io.BytesIO())],
            [TimeoutError('timed out')], [URLError('connection reset')],
            [self.response({'name': []})],
            [io.BytesIO(b'{"candidates":{"unexpected":"shape"}}')],
            [HTTPError('https://example.com', 429, 'quota', {'Retry-After': '2'}, io.BytesIO())],
        ]
        for preceding in failures:
            with self.subTest(failures=preceding):
                model = Gemini(Settings(api_key='TEST'))
                with patch('urllib.request.urlopen', side_effect=[*preceding, self.response({'name': 'Recovered'})]), patch('reputation.providers.time.sleep') as sleep:
                    result = model.generate('test', {}, schema)
                self.assertEqual(result, {'name': 'Recovered'})
                self.assertEqual(model.usage['calls'], len(preceding) + 1)
                self.assertEqual(sleep.call_count, len(preceding))

    def test_permanent_errors_and_long_retry_after_are_not_retried(self):
        for code, headers in [(400, {}), (401, {}), (403, {}), (404, {}),
                              (429, {'Retry-After': '120'}), (503, {'Retry-After': 'Wed, 01 Jan 2099 00:00:00 GMT'})]:
            with self.subTest(code=code, headers=headers):
                model = Gemini(Settings(api_key='TEST'))
                with patch('urllib.request.urlopen', side_effect=HTTPError('https://example.com', code, 'error', headers, io.BytesIO())), patch('reputation.providers.time.sleep') as sleep:
                    with self.assertRaises(ProviderError): model.generate('test', {}, {'type': 'object', 'properties': {}})
                self.assertEqual(model.usage['calls'], 1)
                sleep.assert_not_called()

    def test_deadline_prevents_another_model_attempt(self):
        model = Gemini(Settings(api_key='TEST'))
        model.deadline = time.monotonic() - 1
        with patch('urllib.request.urlopen') as request:
            with self.assertRaises(ProviderError) as caught:
                model.generate('test', {}, {'type': 'object', 'properties': {}})
        self.assertEqual(caught.exception.code, 'time_budget')
        request.assert_not_called()

    def test_local_and_credential_urls_rejected(self):
        for url in ['http://localhost/a', 'http://127.0.0.1', 'http://10.0.1.1', 'http://[::1]/',
                    'http://host.internal/', 'file:///etc/passwd', 'https://user:secret@example.com/',
                    'http://169.254.169.254/', 'https://example.com:9000', 'http://127.1/',
                    'http://0177.0.0.1/', 'https://example.com\n/private']:
            self.assertIsNone(public_url(url), url)
        self.assertEqual(public_url('https://example.com/news#section'), 'https://example.com/news')

    def test_model_shape_validation(self):
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name'], 'additionalProperties': False}
        for value in [{'name': []}, {}, {'name': 'ok', 'extra': 'no'}, []]:
            self.assertFalse(schema_matches(value, schema))
        self.assertTrue(schema_matches({'name': 'ok'}, schema))

    def test_nonfree_price_stops_before_run(self):
        search = MonidSearch(Settings())
        with patch.object(search, '_command', return_value={'provider': 'tinyfish', 'endpoint': '/search', 'price': {'type': 'PER_CALL', 'amount': {'value': .01, 'currency': 'USD'}}}) as command:
            with self.assertRaises(ProviderError) as caught: search.search('test')
            self.assertEqual(caught.exception.code, 'search_price')
            self.assertEqual(command.call_count, 1)
            self.assertTrue(search.blocked)

    def test_billing_uncertainty_blocks_further_calls(self):
        price = {'type': 'PER_CALL', 'amount': {'value': 0, 'currency': 'USD'}}
        search = MonidSearch(Settings())
        with patch.object(search, '_command', side_effect=[{'provider': 'tinyfish', 'endpoint': '/search', 'price': price}, {'status': 'COMPLETED', 'price': price, 'output': {'results': []}}]):
            with self.assertRaises(ProviderError): search.search('test')
        self.assertTrue(search.blocked)

    def test_quota_error_never_echoes_provider_body_or_key(self):
        model = Gemini(Settings(api_key='TEST-SECRET', max_model_attempts=1))
        failure = HTTPError('https://example.com', 429, 'error', {}, io.BytesIO(b'TEST-SECRET and private content'))
        with patch('urllib.request.urlopen', side_effect=failure):
            with self.assertRaises(ProviderError) as caught: model.generate('test', {}, {'type': 'object', 'properties': {}})
        self.assertEqual(caught.exception.code, 'quota')
        self.assertNotIn('TEST-SECRET', str(caught.exception))
        self.assertEqual(model.usage['calls'], 1)

    def test_transient_errors_retry_within_budget(self):
        model = Gemini(Settings(api_key='TEST', max_model_calls=2))
        def fail(*args, **kwargs): raise HTTPError('https://example.com', 503, 'unavailable', {}, io.BytesIO())
        with patch('urllib.request.urlopen', side_effect=fail), patch('reputation.providers.time.sleep'):
            with self.assertRaises(ProviderError): model.generate('test', {}, {'type': 'object', 'properties': {}})
        self.assertEqual(model.usage['calls'], 2)

    def test_gemini_request_uses_schema_and_keeps_key_out_of_url(self):
        model = Gemini(Settings(api_key='TEST-SECRET'))
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name'], 'additionalProperties': False}
        reply = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"name":"Example Company"}'}]}}],
                 'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 10}}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(reply).encode())) as request:
            result = model.generate('Extract a name.', {'text': 'Example Company'}, schema)
        self.assertEqual(result, {'name': 'Example Company'})
        sent = request.call_args.args[0]; body = json.loads(sent.data)
        self.assertEqual(body['generationConfig']['responseJsonSchema'], schema)
        self.assertNotIn('TEST-SECRET', sent.full_url); self.assertNotIn('TEST-SECRET', json.dumps(body))
        self.assertNotIn('tools', body)
        self.assertEqual(model.usage['input_tokens'], 100)

    def test_invalid_model_fields_are_not_coerced_into_real_results(self):
        model = Gemini(Settings(api_key='TEST', max_model_attempts=1))
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']}
        reply = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"name": []}'}]}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(reply).encode())):
            with self.assertRaises(ProviderError) as caught: model.generate('test', {}, schema)
        self.assertEqual(caught.exception.code, 'model_format')

    def test_truncated_model_answer_is_not_accepted(self):
        model = Gemini(Settings(api_key='TEST', max_model_attempts=1))
        reply = {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{}'}]}}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(reply).encode())):
            with self.assertRaises(ProviderError) as caught: model.generate('test', {}, {'type': 'object', 'properties': {}})
        self.assertEqual(caught.exception.code, 'model_incomplete')


class FixtureSearch:
    def search(self, query): return [{'url': p['url']} for p in pages().values()]
    def fetch(self, urls):
        return [{'url': p['url'], 'text': p['text'], 'published_date': p['published_at']} for p in pages().values() if p['url'] in urls], []


class FixtureModel:
    def __init__(self, needs_followup=False):
        self.usage = {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'thinking_tokens': 0}
    def generate(self, instruction, data, schema):
        self.usage['calls'] += 1
        if 'candidates' in schema['properties']:
            return {'candidates': [{**CANDIDATE, 'source_id': list(pages())[0], 'quote': TEXT1}]}
        return record()


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(api_key='TEST-NOT-REAL', db_path=Path(self.temp.name) / 'test.sqlite')
        self.store = Store(self.settings.db_path)
        self.service = ResearchService(self.settings, self.store, FixtureSearch(), FixtureModel)
        self.app = create_app(self.settings, self.service)

    def tearDown(self):
        self.service.pool.shutdown(wait=True)
        self.temp.cleanup()

    def wait_job(self, job):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            saved = self.store.get_job(job['id'])
            if saved['status'] not in ('queued', 'running') and not self.service.active: return saved
            time.sleep(.01)
        self.fail('Fixture job did not finish')

    def request(self, path, method='GET', data=None, **extra):
        body = json.dumps(data).encode() if data is not None else b''
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'HTTP_HOST': '127.0.0.1:8787', 'wsgi.url_scheme': 'http',
               'wsgi.input': io.BytesIO(body), 'CONTENT_LENGTH': str(len(body)), 'CONTENT_TYPE': 'application/json', **extra}
        response = {}; raw = b''.join(self.app(env, lambda status, headers: response.update(status=int(status.split()[0]), headers=dict(headers))))
        return response['status'], json.loads(raw) if raw else None

    def test_button_api_completes_and_fresh_result_reused(self):
        status, result = self.request('/api/reputation/jobs', 'POST', {'count': 1, 'mode': 'live'})
        self.assertEqual(status, 202)
        job = self.wait_job(result)
        self.assertEqual(job['status'], 'completed'); self.assertEqual(job['cards'][0]['name'], 'Example Company')
        self.assertEqual(job['review_cards'], []); self.assertEqual(job['metrics']['model_calls'], 2)
        status, repeated = self.request('/api/reputation/jobs', 'POST', {'count': 1, 'mode': 'live'})
        self.assertEqual(status, 200); self.assertTrue(repeated['reused']); self.assertEqual(repeated['id'], job['id'])

    def test_idempotent_post_reuses_active_completed_and_failed_jobs(self):
        gate, entered = threading.Event(), threading.Event()
        class BlockingModel(FixtureModel):
            def generate(self, *args):
                entered.set(); gate.wait(3); return super().generate(*args)
        self.service.model_factory = BlockingModel
        data = {'count': 1, 'request_id': 'test-idempotency-0001'}
        status, first = self.request('/api/reputation/jobs', 'POST', data)
        self.assertEqual(status, 202); entered.wait(1)
        try:
            status, repeated = self.request('/api/reputation/jobs', 'POST', data)
            self.assertEqual(status, 200); self.assertEqual(first['id'], repeated['id'])
            status, conflict = self.request('/api/reputation/jobs', 'POST', {**data, 'count': 2})
            self.assertEqual(status, 409); self.assertEqual(conflict['code'], 'request_conflict')
        finally:
            gate.set()
        job = self.wait_job(first)
        self.assertEqual(job['metrics']['model_calls'], 2)
        for state in ('completed', 'failed'):
            job['status'] = state; self.store.save_job(job)
            status, repeated = self.request('/api/reputation/jobs', 'POST', data)
            self.assertEqual(status, 200); self.assertEqual(repeated['id'], job['id'])
        self.assertEqual(len(self.store.recent()), 1)

    def test_new_request_id_is_remembered_when_completed_job_is_cached(self):
        first = self.wait_job(self.service.start(count=1)[0])
        cached, reused = self.service.start(count=1, request_id='cached-request-0001')
        self.assertTrue(reused)
        cached['status'] = 'failed'; self.store.save_job(cached)
        repeated, reused = self.service.start(count=1, request_id='cached-request-0001')
        self.assertTrue(reused); self.assertEqual(repeated['id'], first['id'])

    def test_search_and_page_retrieval_recover_from_transient_errors(self):
        search = self.service.search
        real_search, real_fetch = search.search, search.fetch
        with patch.object(search, 'search', side_effect=[ProviderError('search_connection', 'Temporary outage.'), real_search('test'), *[real_search('test')] * 8]) as searches, patch.object(search, 'fetch', side_effect=[ProviderError('search_connection', 'Temporary outage.'), real_fetch([p['url'] for p in pages().values()])]) as fetches, patch('reputation.engine.time.sleep'):
            job = self.wait_job(self.service.start(count=1)[0])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(fetches.call_count, 2)
        self.assertEqual(job['metrics']['pages_fetched'], 4)
        self.assertEqual(job['metrics']['searches'], searches.call_count)
        self.assertTrue(any('retrying automatically' in w for w in job['warnings']))

    def test_retrieval_retries_cannot_exceed_global_budgets(self):
        for kind in ('search', 'fetch'):
            with self.subTest(kind=kind):
                self.settings.max_searches = 2 if kind == 'search' else 14
                self.settings.max_pages = 2
                with patch.object(self.service.search, kind, side_effect=ProviderError('search_connection', 'Temporary outage.')) as provider, patch('reputation.engine.time.sleep'):
                    job = self.wait_job(self.service.start(count=1)[0])
                self.assertEqual(job['status'], 'failed')
                self.assertLessEqual(job['metrics']['searches'], self.settings.max_searches)
                self.assertLessEqual(job['metrics']['pages_fetched'], self.settings.max_pages)
                self.assertEqual(provider.call_count, 2 if kind == 'search' else 1)

    def test_model_failure_during_followup_preserves_verified_card(self):
        class GapSearch(FixtureSearch):
            def search(self, query):
                values = list(pages().values())
                return [{'url': values[1 if 'industrial collaboration gap' in query else 0]['url']}]
        class PartialModel(FixtureModel):
            def generate(self, instruction, data, schema):
                if self.usage['calls'] >= 2:
                    raise ProviderError('model_unavailable', 'Temporarily unavailable.')
                result = super().generate(instruction, data, schema)
                if 'signals' in result:
                    result['signals'] = result['signals'][:1]
                    result['follow_up_query'] = 'Example Company industrial collaboration gap'
                return result
        self.service.search = GapSearch(); self.service.model_factory = PartialModel
        job = self.wait_job(self.service.start(count=1)[0])
        self.assertEqual(job['status'], 'partial')
        self.assertEqual(len(job['review_cards'][0]['signals']), 1)
        self.assertEqual(job['error_code'], 'model_unavailable')

    def test_provider_initialization_failure_does_not_leave_worker_stuck(self):
        def broken(): raise RuntimeError('private failure')
        self.service.model_factory = broken
        job = self.wait_job(self.service.start(count=1)[0])
        self.assertEqual(job['status'], 'failed'); self.assertEqual(job['error_code'], 'internal_error')
        self.assertNotIn('private failure', job['error'])
        self.service.model_factory = FixtureModel
        self.assertEqual(self.wait_job(self.service.start(count=1)[0])['status'], 'completed')

    def test_insufficient_results_remain_partial_not_padded(self):
        job = self.wait_job(self.service.start(count=3)[0])
        self.assertEqual(job['status'], 'partial'); self.assertEqual(len(job['cards']), 1)

    def test_model_failure_is_visible_without_fake_sample_fallback(self):
        class FailedModel(FixtureModel):
            def generate(self, *args): raise ProviderError('quota', 'Quota reached.')
        self.service.model_factory = FailedModel
        job = self.wait_job(self.service.start(count=1)[0])
        self.assertEqual(job['status'], 'failed'); self.assertEqual(job['mode'], 'live'); self.assertEqual(job['cards'], [])
        self.assertEqual(job['error_code'], 'quota'); self.assertGreater(len(job['sources']), 0)

    def test_followup_runs_internally_and_improves_shortlist(self):
        class GapSearch(FixtureSearch):
            def search(self, query):
                values = list(pages().values())
                return [{'url': values[1 if 'industrial collaboration gap' in query else 0]['url']}]
        class GapModel(FixtureModel):
            def generate(self, instruction, data, schema):
                result = super().generate(instruction, data, schema)
                if 'signals' in result and len(data['sources']) < 2:
                    result['signals'] = result['signals'][:1]
                    result['follow_up_query'] = 'Example Company industrial collaboration gap'
                return result
        self.service.search = GapSearch(); self.service.model_factory = GapModel
        job = self.wait_job(self.service.start(count=1)[0])
        self.assertEqual(job['status'], 'completed'); self.assertEqual(job['metrics']['model_calls'], 3)
        self.assertTrue(any('Resolving evidence gaps' in e['message'] for e in job['events']))
        self.assertEqual(len(job['cards'][0]['signals']), 2); self.assertEqual(job['review_cards'], [])

    def test_saved_research_is_labeled_and_uses_no_model_calls(self):
        self.settings.api_key = ''
        job = self.wait_job(self.service.start(count=3, mode='sample')[0])
        self.assertEqual(job['status'], 'completed'); self.assertEqual(job['mode'], 'sample')
        self.assertEqual(job['metrics']['model_calls'], 0); self.assertEqual(job['metrics']['searches'], 0)
        self.assertTrue(job['cards'] or job['review_cards'])
        self.assertTrue(all('Saved assistant-curated' in c['assessment_method'] for c in job['cards'] + job['review_cards']))

    def test_active_job_reused_by_conflict_without_duplicate_work(self):
        gate, entered = threading.Event(), threading.Event()
        class BlockingModel(FixtureModel):
            def generate(self, *args):
                entered.set(); gate.wait(3); return super().generate(*args)
        self.service.model_factory = BlockingModel
        job = self.service.start(count=1)[0]; entered.wait(1)
        try:
            status, result = self.request('/api/reputation/jobs', 'POST', {'count': 1})
            self.assertEqual(status, 409); self.assertEqual(result['id'], job['id'])
        finally: gate.set()
        self.wait_job(job)

    def test_recovery_retains_evidence_and_cache(self):
        job = self.wait_job(self.service.start(count=1)[0]); job['status'] = 'running'; self.store.save_job(job)
        self.store.recover(); saved = self.store.get_job(job['id'])
        self.assertEqual(saved['status'], 'interrupted'); self.assertEqual(len(saved['cards']), 1)
        self.assertIsNotNone(self.store.cached_page('https://university.example/news', 100))

    def test_no_secret_or_local_file_endpoint(self):
        status, data = self.request('/api/reputation/status'); self.assertEqual(status, 200)
        self.assertNotIn('TEST-NOT-REAL', json.dumps(data))
        self.assertEqual(self.request('/.env.local')[0], 404)
        self.assertEqual(self.request('/reputation/../.env.local')[0], 404)

    def test_cross_origin_invalid_count_and_host_rejected(self):
        self.assertEqual(self.request('/api/reputation/jobs', 'POST', {'count': 1}, HTTP_ORIGIN='https://untrusted.example')[0], 403)
        self.assertEqual(self.request('/api/reputation/jobs', 'POST', {'count': True})[0], 400)
        self.assertEqual(self.request('/api/reputation/jobs', 'POST', {'count': 500})[0], 400)
        self.assertEqual(self.request('/api/reputation/status', HTTP_HOST='attacker.example')[0], 403)

    def test_remote_mount_requires_access_token(self):
        self.settings.access_token = 'TEST-ACCESS'
        self.assertEqual(self.request('/api/reputation/jobs', HTTP_HOST='site.example')[0], 401)
        self.assertEqual(self.request('/api/reputation/jobs', HTTP_HOST='site.example', HTTP_AUTHORIZATION='Bearer TEST-ACCESS')[0], 200)


if __name__ == '__main__': unittest.main()
