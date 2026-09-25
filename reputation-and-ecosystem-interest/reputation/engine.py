"""Bounded research jobs. Search snippets discover URLs; full pages support claims."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import threading
import time
import uuid

from .config import ROOT
from .evidence import (assess, check_candidates, make_page, merge_assessments, norm, now_iso,
                       rank_card, short_company_name, source_family)
from .providers import Gemini, MonidSearch, ProviderError, public_url
from .schemas import DISCOVERY, DISCOVERY_INSTRUCTION, ASSESSMENT, ASSESSMENT_INSTRUCTION

PIPELINE_VERSION = '1.1.0'


class BusyError(Exception):
    def __init__(self, job_id):
        self.job_id = job_id


class ResearchService:
    def __init__(self, settings, store, search=None, model_factory=None):
        self.settings, self.store = settings, store
        self.search = search or MonidSearch(settings)
        self.model_factory = model_factory or (lambda: Gemini(settings))
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='reputation')
        self.lock = threading.Lock()
        self.active = None
        self.store.recover()

    def start(self, count=3, sector='All sectors', mode='live', request_id=None):
        with self.lock:
            if request_id:
                prior = self.store.job_for_request(request_id)
                if prior:
                    if (prior['requested_count'], prior['sector'], prior['mode']) != (count, sector, mode):
                        raise ProviderError('request_conflict', 'This request ID was already used with different parameters. Use a new request ID.')
                    return prior, True
            if self.active:
                raise BusyError(self.active)
            # Repeated clicks reuse completed fresh jobs. Errors and incomplete jobs
            # are never silently substituted for a requested live run.
            for prior in self.store.recent():
                if (prior['status'] == 'completed' and prior['mode'] == mode
                        and prior.get('pipeline_version') == PIPELINE_VERSION
                        and prior.get('model') == (self.settings.model if mode == 'live' else None)
                        and prior['requested_count'] == count and prior['sector'] == sector
                        and time.time() - prior['created_epoch'] < 900):
                    self.store.remember_request(request_id, prior['id'])
                    return prior, True
            if sum(j['mode'] == 'live' and time.time() - j['created_epoch'] < 3600
                   for j in self.store.recent(30)) >= 10 and mode == 'live':
                raise ProviderError('job_limit', 'The hourly research limit was reached. Reuse a saved run or try later.')
            if mode == 'live' and not self.settings.api_key:
                raise ProviderError('missing_key', 'Configure GEMINI_API_KEY on the backend to start live research.')
            job = {'id': uuid.uuid4().hex, 'request_id': request_id, 'pipeline_version': PIPELINE_VERSION, 'status': 'queued', 'stage': 'Preparing research',
                   'created_at': now_iso(), 'created_epoch': time.time(), 'updated_at': now_iso(),
                   'requested_count': count, 'sector': sector, 'mode': mode, 'model': self.settings.model if mode == 'live' else None,
                   'cards': [], 'review_cards': [], 'sources': [], 'events': [], 'warnings': [],
                   'metrics': {'searches': 0, 'pages_fetched': 0, 'cache_hits': 0, 'model_calls': 0},
                   'error': None, 'qualified_count': 0,
                   'public_interest_trend': 'not_measured'}
            self.store.save_job(job)
            self.active = job['id']
            self.pool.submit(self._execute, job)
            return job, False

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _execute(self, job):
        run = None
        try:
            run = Run(self, job)
            if job['mode'] == 'sample':
                run.sample()
            else:
                run.live()
        except ProviderError as exc:
            job['error'] = str(exc)
            job['error_code'] = exc.code
            job['status'] = 'partial' if job['cards'] or job['review_cards'] else 'failed'
            job['stage'] = 'Partial results saved' if job['status'] == 'partial' else 'Research needs attention'
        except Exception:
            # No traceback/provider body in a public job record.
            job['error'] = 'Research stopped unexpectedly. Available evidence was saved. Start a new run to retry.'
            job['error_code'] = 'internal_error'
            job['status'] = 'partial' if job['cards'] or job['review_cards'] else 'failed'
            job['stage'] = 'Research interrupted'
        finally:
            try:
                if run:
                    run.persist()
                else:
                    self.store.save_job(job)
            finally:
                with self.lock:
                    self.active = None


class Run:
    def __init__(self, service, job):
        self.service, self.job = service, job
        self.settings, self.store = service.settings, service.store
        self.model = service.model_factory()
        self.pages, self.cards = {}, []
        self.started = time.monotonic()
        self.model.deadline = self.started + self.settings.max_seconds
        self.model.on_status = self.model_status

    def model_status(self, message):
        self.job['events'].append({'at': now_iso(), 'message': message})
        self.persist()

    def persist(self):
        self.job['updated_at'] = now_iso()
        self.job['metrics']['model_calls'] = self.model.usage['calls']
        self.job['metrics']['model_usage'] = dict(self.model.usage)
        self.job['sources'] = [{k: v for k, v in p.items() if k != 'text'} for p in self.pages.values()]
        self.store.save_job(self.job)

    def progress(self, stage, detail=None):
        self.job.update(status='running', stage=stage)
        self.job['events'].append({'at': now_iso(), 'message': detail or stage})
        self.persist()

    def warn(self, message):
        if message not in self.job['warnings']:
            self.job['warnings'].append(message)
        self.persist()

    def budget(self):
        if time.monotonic() - self.started >= self.settings.max_seconds:
            raise ProviderError('time_budget', 'The research time limit was reached. Available findings are saved.')

    def search(self, query):
        self.budget()
        if self.job['metrics']['searches'] >= self.settings.max_searches:
            raise ProviderError('search_budget', 'The search limit was reached. Available findings are saved.')
        for attempt in range(3):
            self.budget()
            if self.job['metrics']['searches'] >= self.settings.max_searches:
                raise ProviderError('search_budget', 'The search limit was reached. Available findings are saved.')
            self.job['metrics']['searches'] += 1
            self.job['events'].append({'at': now_iso(), 'message': ('Retrying search: ' if attempt else 'Searching: ') + query})
            self.persist()
            try:
                return self.service.search.search(query)
            except ProviderError as exc:
                if exc.code in ('search_price', 'search_setup'):
                    raise
                if attempt < 2:
                    self.warn('Search temporarily unavailable; retrying automatically.')
                    time.sleep(2 ** attempt)
                else:
                    self.warn(str(exc) + ' This is a retrieval failure, not evidence that a company lacks activity.')
        return []

    def fetch(self, results, maximum=3):
        self.budget()
        urls = []
        skip_hosts = ('linkedin.com', 'facebook.com', 'instagram.com', 'crunchbase.com', 'pitchbook.com')
        for result in results:
            url = public_url(result.get('url', ''))
            if not url or any(host in url.split('/')[2] for host in skip_hosts):
                continue
            if any(p['url'] == url or p.get('requested_url') == url for p in self.pages.values()):
                continue
            if url not in urls:
                urls.append(url)
            if len(urls) == maximum:
                break
        pending = []
        for url in urls:
            cached = self.store.cached_page(url, self.settings.page_cache_seconds)
            if cached:
                checked = make_page({'url': cached.get('requested_url', cached['url']),
                                     'final_url': cached['url'], 'text': cached['text'],
                                     'title': cached['title'], 'published_date': cached.get('published_at')})
                if checked:
                    checked['observed_at'] = cached['observed_at']
                    self.pages[checked['id']] = checked
                    self.job['metrics']['cache_hits'] += 1
                else:
                    self.warn('An unreadable or access-blocked cached page was excluded from evidence.')
            else:
                pending.append(url)
        if pending:
            pages, errors = [], []
            for attempt in range(3):
                self.budget()
                available = self.settings.max_pages - self.job['metrics']['pages_fetched']
                pending = pending[:max(0, available)]
                if not pending:
                    self.warn('The page-fetch limit was reached. Available evidence is retained.')
                    break
                # Retries consume the same global page budget as initial attempts.
                self.job['metrics']['pages_fetched'] += len(pending)
                self.persist()
                try:
                    pages, errors = self.service.search.fetch(pending)
                    break
                except ProviderError as exc:
                    if exc.code in ('search_price', 'search_setup'):
                        raise
                    if attempt < 2 and self.job['metrics']['pages_fetched'] < self.settings.max_pages:
                        self.warn('Source retrieval temporarily unavailable; retrying automatically.')
                        time.sleep(2 ** attempt)
                    else:
                        self.warn(str(exc) + ' Unread source pages are not used as evidence.')
                        break
            for raw in pages:
                page = make_page(raw)
                if page:
                    self.pages[page['id']] = page
                    self.store.cache_page(page)
                else:
                    self.warn('An unreadable or access-blocked page was excluded from evidence.')
            if errors:
                self.warn(f'{len(errors)} source page(s) could not be read; their snippets are not used as evidence.')
        self.persist()

    def documents(self, candidate=None):
        pages = list(self.pages.values())
        if candidate:
            names = [candidate['name'], *candidate.get('aliases', [])]
            pages = [p for p in pages if any(norm(name) in norm(p['text']) for name in names)]
        # Slice around the company so long directories retain the relevant passage.
        docs = []
        for page in pages[:12]:
            text = page['text']
            if candidate and len(text) > 18000:
                index = text.casefold().find(candidate['name'].casefold())
                start = max(0, index - 5000)
                text = text[start:start + 18000]
            else:
                text = text[:18000]
            docs.append({'id': page['id'], 'url': page['url'], 'title': page['title'],
                         'published_at': page.get('published_at'), 'text': text})
        return docs

    def publish_cards(self):
        ranked = sorted(self.cards, key=lambda c: c['_rank'], reverse=True)
        qualified = [c for c in ranked if c['qualified']]
        review = [c for c in ranked if not c['qualified']]
        self.job['qualified_count'] = len(qualified)
        self.job['cards'] = [{k: v for k, v in c.items() if not k.startswith('_')} for c in qualified[:self.job['requested_count']]]
        self.job['review_cards'] = [{k: v for k, v in c.items() if not k.startswith('_')} for c in review]
        self.persist()

    def live(self):
        self.progress('Discovering NJ companies')
        sector = '' if self.job['sector'] == 'All sectors' else self.job['sector']
        queries = [f'site:njeda.gov startups awardees {sector}'.strip(),
                   f'startup "Rutgers" "exclusive license" {sector}'.strip(),
                   f'site:hax.co "Newark" "company" {sector}'.strip()]
        for query in queries:
            self.fetch(self.search(query), maximum=2)
        if not self.pages:
            raise ProviderError('no_sources', 'No source pages were retrieved. Check search service availability and try again.')
        self.progress('Identifying company candidates')
        self.budget()
        discovery = self.model.generate(DISCOVERY_INSTRUCTION,
                    {'date': now_iso()[:10], 'requested_count': min(self.job['requested_count'] + 2, 7),
                     'sector_filter': self.job['sector'], 'sources': self.documents()}, DISCOVERY)
        candidates = check_candidates(discovery, self.pages, self.job['requested_count'] + 2)
        if self.job['sector'] != 'All sectors':
            candidates = [c for c in candidates if c['sector'] == self.job['sector']]
        self.job['candidate_count'] = len(candidates)
        for candidate in candidates:
            self.budget()
            if self.model.usage['calls'] >= self.settings.max_model_calls:
                break
            name = candidate['name']
            search_name = short_company_name(name)
            self.progress('Checking ' + name)
            self.fetch(self.search('"' + search_name + '"'), maximum=3)
            # A short second query seeks evidence beyond the company's own site.
            self.fetch(self.search('"' + search_name + '" partnership accelerator New Jersey'), maximum=2)
            data = {'date': now_iso()[:10], 'company': candidate, 'sources': self.documents(candidate)}
            raw = self.model.generate(ASSESSMENT_INSTRUCTION, data, ASSESSMENT)
            try:
                card = assess(candidate, raw, self.pages)
            except ValueError:
                self.warn('A mismatched company record was excluded.')
                continue
            follow_up = card['follow_up_query']
            # Resolve consequential gaps within this same run, without user prompts.
            if (follow_up and not card['qualified'] and self.model.usage['calls'] < self.settings.max_model_calls
                    and self.job['metrics']['searches'] < self.settings.max_searches):
                self.cards.append(card)
                self.publish_cards()
                self.progress('Resolving evidence gaps for ' + name)
                # Constrain model-generated queries to the company being researched.
                query = follow_up if norm(name) in norm(follow_up) else '"' + name + '" ' + follow_up
                before = len(self.pages)
                self.fetch(self.search(query), maximum=2)
                if len(self.pages) > before:
                    data['sources'] = self.documents(candidate)
                    data['prior_assessment'] = {k: v for k, v in card.items() if not k.startswith('_')}
                    raw = self.model.generate(ASSESSMENT_INSTRUCTION, data, ASSESSMENT)
                    try:
                        card = merge_assessments(card, assess(candidate, raw, self.pages))
                    except ValueError:
                        self.warn('A follow-up returned a mismatched identity; earlier findings were retained.')
                self.cards.pop()
            self.cards.append(card)
            self.publish_cards()
            if self.job['qualified_count'] >= self.job['requested_count']:
                break
        self.publish_cards()
        enough = self.job['qualified_count'] >= self.job['requested_count']
        self.job['status'] = 'completed' if enough else 'partial'
        self.job['stage'] = 'Research complete' if enough else 'Research complete with evidence gaps'
        if not enough:
            self.job['warnings'].append('The bounded run found fewer qualified companies than requested. Review candidates are shown separately; the list was not padded.')
        self.persist()

    def sample(self):
        """Load the three real, saved pilot cards. No provider call or fake live data."""
        self.progress('Loading saved public-source research')
        base = ROOT / 'research' / 'nj-momentum-2026-09-25'
        sources = json.loads((base / 'sources.json').read_text())
        for source in sources:
            path = (base / source['snapshot_path']).resolve()
            if not path.is_relative_to(base.resolve()):
                raise ProviderError('sample_integrity', 'Invalid saved source path.')
            text = path.read_text()
            if hashlib.sha256(text.encode()).hexdigest() != source['sha256']:
                raise ProviderError('sample_integrity', 'A saved source failed its integrity check.')
            self.pages[source['id']] = {'id': source['id'], 'url': source['url'], 'title': source['title'],
                'text': text, 'published_at': source.get('published_at', '')[:10] if source.get('published_at') else None,
                'observed_at': source['observed_at'], 'sha256': source['sha256'],
                'source_family': source_family(source['url']), 'provenance': 'public'}
        report = json.loads((base / 'results.json').read_text())
        mappings = {'university_technology_relationship': ('technology_license', 'Rutgers'),
                    'investor_affiliation': ('investor_affiliation', 'Clean Energy Ventures'),
                    'strategic_partner_affiliation': ('industrial_partnership', 'Buzzi Unicem USA'),
                    'industry_recognition': ('award', 'Edison Patent Awards'),
                    'accelerator_selection': ('accelerator_participation', 'NJ AI Hub'),
                    'founder_university_affiliation': ('community_activity', 'NJIT'),
                    'community_engagement': ('community_activity', 'NJIT'),
                    'competition_recognition': ('award', 'NJIT'),
                    'research_institution_collaboration': ('research_collaboration', 'NETL'),
                    'public_program_selection': ('program_selection', 'NJEDA / CSIT')}
        for old in report['companies']:
            sector = 'Life sciences' if 'Chorah' in old['company'] else 'Climate & materials'
            if self.job['sector'] not in ('All sectors', sector):
                continue
            raw = {'name': old['company'], 'official_domain': '', 'sector': sector,
                   'description': ' / '.join(old.get('sector_tags', [])),
                   'nj_presence': {'status': 'ecosystem_only' if 'Chorah' in old['company'] else 'operations',
                                   'location': old['nj_presence']['connection_type'],
                                   'evidence': old['nj_presence']['evidence']},
                   'signals': [], 'uncertainties': old.get('limitations', []), 'follow_up_query': ''}
            for signal in old['signals']:
                kind, org = mappings.get(signal['type'], ('program_selection', 'Named institution'))
                statement = signal.get('statement', '')
                for evidence in signal.get('evidence', [])[:1]:
                    raw['signals'].append({'type': kind, 'organization': org, 'statement': statement,
                        'event_date': signal.get('event_date') or '', 'event_key': signal.get('event_group', kind),
                        'status': 'historical', 'source_role': 'institution_confirmation',
                        'source_id': evidence['source_id'], 'quote': evidence['quote']})
            aliases = ['Cecilia', 'Cecilia Energy'] if 'Cecilia' in old['company'] else []
            card = assess({'name': old['company'], 'aliases': aliases, 'sector': sector}, raw, self.pages)
            card['assessment_method'] = 'Saved assistant-curated research; current backend quote checks and ranking rules. No live search or Gemini call.'
            card['limitations'].insert(0, 'Saved pilot from September 25, 2026. This is not a fresh search.')
            self.cards.append(card)
        self.publish_cards()
        self.job.update(status='completed', stage='Saved research loaded')
        self.job['warnings'].append('Saved research preview. No new searches, model requests or freshness claims.')
        self.persist()
