"""Deterministic provenance, identity, date and ranking checks."""
from datetime import date, datetime, timezone
import calendar
from difflib import SequenceMatcher
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit

from .providers import public_url
from .schemas import SIGNAL_TYPES, SECTORS


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def norm(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value).casefold()).strip()


def clean(value, limit=500):
    return value[:limit].strip() if isinstance(value, str) else ''


def source_family(url):
    host = (urlsplit(url).hostname or '').removeprefix('www.')
    for family, domains in {'sosv-hax': ['hax.co', 'sosv.com'],
                            'njeda-csit': ['njeda.gov', 'njcsit.gov']}.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return family
    return '.'.join(host.split('.')[-2:])


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', value):
        return None
    try:
        parts = value.split('-')
        parsed = date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 1,
                      int(parts[2]) if len(parts) > 2 else 1)
        return parsed if parsed <= date.today() else None
    except ValueError:
        return None


def publication_date(value):
    if isinstance(value, str):
        candidate = value[:10]
        if parse_date(candidate):
            return candidate
    return None


def supported_event_date(value, quote):
    """Do not infer month/day precision from a quotation that only names a year."""
    if not parse_date(value) or value[:4] not in quote:
        return None
    if len(value) == 4 or value in quote:
        return value
    parts = value.split('-'); year, month = parts[0], int(parts[1])
    month_word = rf'{calendar.month_abbr[month]}(?:{calendar.month_name[month][3:]})?\.?'
    if len(parts) == 3:
        day = int(parts[2]); suffix = r'(?:st|nd|rd|th)?'
        if re.search(rf'\b(?:{month_word}\s+0?{day}{suffix},?\s+{year}|0?{day}{suffix}\s+{month_word}\s+{year})\b', quote, re.I):
            return value
    if re.search(rf'\b{month_word}\s+{year}\b', quote, re.I) or value[:7] in quote:
        return value[:7]
    return year


def make_page(raw):
    url = public_url(raw.get('final_url') or raw.get('url', ''))
    if not url:
        return None
    try:
        ipaddress.ip_address(urlsplit(url).hostname)
        # CDN/IP redirects must not turn one institution into two source families.
        url = public_url(raw.get('url', '')) or url
    except ValueError:
        pass
    text = raw.get('text', '')
    if not isinstance(text, str) or len(text) < 50:
        return None
    if re.search(r'checking your browser|access denied|just a moment|captcha', raw.get('title', ''), re.I):
        return None
    return {'id': 'S' + hashlib.sha256(url.encode()).hexdigest()[:12],
            'url': url, 'requested_url': raw.get('url', url),
            'title': clean(raw.get('title', ''), 250), 'text': text[:180000],
            'published_at': publication_date(raw.get('published_date')),
            'observed_at': now_iso(), 'source_family': source_family(url),
            'sha256': hashlib.sha256(text[:180000].encode()).hexdigest(), 'provenance': 'public'}


def verify_quote(item, pages):
    if not isinstance(item, dict):
        return None
    page = pages.get(item.get('source_id'))
    quote = item.get('quote')
    if not page or not isinstance(quote, str) or not 16 <= len(quote) <= 2400:
        return None
    start = page['text'].find(quote)
    if start < 0:
        return None
    return {'source_id': page['id'], 'quote': quote, 'start_offset': start,
            'end_offset': start + len(quote), 'url': page['url'], 'title': page['title'],
            'published_at': page.get('published_at'), 'observed_at': page['observed_at'],
            'source_family': page['source_family'], 'snapshot_sha256': page['sha256']}


def candidate_key(name, domain=''):
    # Do not collapse differently named entities merely because they share a site.
    return 'company-' + hashlib.sha256((norm(name) + '|' + domain.lower()).encode()).hexdigest()[:16]


def short_company_name(name):
    return re.sub(r'(?:[,\s]+(?:incorporated|inc\.?|llc\.?|ltd\.?|corporation|corp\.?))+$', '', name, flags=re.I).strip()


def attributed(quote, candidate):
    text = ' ' + norm(quote) + ' '
    names = [candidate['name'], *candidate.get('aliases', [])]
    return any(' ' + norm(name) + ' ' in text for name in names if len(norm(name)) >= 2)


def check_candidates(result, pages, count):
    selected, seen = [], set()
    for item in result.get('candidates', [])[:7]:
        if not isinstance(item, dict):
            continue
        name = clean(item.get('name'), 100)
        quote = item.get('quote', '')
        page = pages.get(item.get('source_id'))
        if (not name or not page or not isinstance(quote, str) or not 16 <= len(quote) <= 2400 or quote not in page['text']
                or norm(name) not in norm(quote) or norm(name) in seen):
            continue
        seen.add(norm(name))
        aliases = [clean(a, 100) for a in item.get('aliases', [])[:4] if len(norm(a)) >= 2]
        short = short_company_name(name)
        if short != name and len(norm(short)) >= 3:
            aliases.append(short)
        selected.append({'name': name, 'aliases': list(dict.fromkeys(aliases)),
                         'sector': item.get('sector') if item.get('sector') in SECTORS else 'Other',
                         'discovery_source_id': page['id']})
        if len(selected) == count:
            break
    return selected


def deduplicate(signals):
    kept = []
    for signal in signals:
        duplicate = None
        for previous in kept:
            same_event = (norm(signal['event_key']) == norm(previous['event_key'])
                          and norm(signal['organization']) == norm(previous['organization'])
                          and signal['type'] == previous['type'])
            same_quote = SequenceMatcher(None, norm(signal['evidence'][0]['quote']),
                                         norm(previous['evidence'][0]['quote'])).ratio() > .88
            if same_event or same_quote:
                duplicate = previous
                break
        if duplicate:
            if signal['evidence'][0]['source_id'] not in {e['source_id'] for e in duplicate['evidence']}:
                duplicate['evidence'].extend(signal['evidence'])
        else:
            kept.append(signal)
    return kept


def assess(candidate, raw, pages):
    warnings, signals = [], []
    if norm(raw.get('name', '')) not in {norm(candidate['name']), *[norm(a) for a in candidate.get('aliases', [])]}:
        raise ValueError('The model returned a different company identity.')
    for item in raw.get('signals', [])[:10]:
        if not isinstance(item, dict):
            continue
        evidence = verify_quote(item, pages)
        if not evidence or item.get('type') not in SIGNAL_TYPES:
            warnings.append('A proposed signal was excluded because its source or exact quotation could not be verified.')
            continue
        # A company name elsewhere on a directory page cannot attribute this quote.
        if not attributed(evidence['quote'], candidate):
            warnings.append('A source without a matching company attribution was excluded.')
            continue
        if item['type'] == 'investor_affiliation' and not re.search(
                r'\b(invest(?:or|ors|ment|ments|ed|ing)?|backed|financ(?:ing|ed)|funding round|led.*round)\b', evidence['quote'], re.I):
            warnings.append('An investor affiliation was excluded because the quote did not establish an investment relationship.')
            continue
        claimed_date = clean(item.get('event_date'), 10)
        event_date = supported_event_date(claimed_date, item['quote']) if claimed_date else None
        if claimed_date and not event_date:
            warnings.append('An unsupported event date was removed; source publication dates remain separate.')
        elif claimed_date and claimed_date != event_date:
            warnings.append('Event-date precision was reduced to what the quotation supports.')
        status = item.get('status') if item.get('status') in ('current', 'historical', 'announced', 'unknown') else 'unknown'
        if item['type'] in ('technology_license', 'research_collaboration', 'industrial_partnership') and re.search(
                r'\b(proposes?|proposed|plans? to|intends? to|will collaborate|will partner)\b', evidence['quote'], re.I):
            status = 'announced'
            warnings.append('Proposal language is retained as planned work, not evidence of completed execution.')
        published = parse_date(evidence.get('published_at'))
        if status == 'current' and published and (date.today() - published).days > 730:
            status = 'historical'
            warnings.append('Older reporting is labeled historical; continuing activity has not been established.')
        signals.append({'type': item['type'], 'organization': clean(item.get('organization'), 150),
                        'statement': clean(item.get('statement'), 600), 'event_date': event_date or None,
                        'event_key': clean(item.get('event_key'), 180) or item['type'] + ':' + norm(item.get('organization', '')),
                        'status': status,
                        'source_role': item.get('source_role') if item.get('source_role') in ('institution_confirmation', 'independent_reporting', 'company_claim', 'directory') else 'company_claim',
                        'evidence': [evidence]})
    signals = deduplicate(signals)
    nj = raw.get('nj_presence', {})
    nj_evidence = [verified for item in nj.get('evidence', [])[:4]
                   if (verified := verify_quote(item, pages)) and attributed(verified['quote'], candidate)]
    nj_status = nj.get('status', 'unclear')
    if nj_status not in ('headquarters', 'operations', 'ecosystem_only', 'unclear', 'outside_nj', 'conflicting'):
        nj_status = 'unclear'
    if not nj_evidence:
        nj_status = 'unclear'
        warnings.append('NJ presence could not be supported by a verified source quotation.')
    elif nj_status == 'headquarters' and not any(re.search(r'\b(headquarter(?:s|ed)?|HQ)\b', e['quote'], re.I) for e in nj_evidence):
        nj_status = 'operations'
        warnings.append('Sources support an NJ location; headquarters status was not explicit in the quotation.')
    domain = clean(raw.get('official_domain'), 200).lower().removeprefix('https://').removeprefix('http://').strip('/').removeprefix('www.')
    if domain and domain not in {(urlsplit(p['url']).hostname or '').removeprefix('www.') for p in pages.values()}:
        domain = ''
        warnings.append('The proposed official domain was not confirmed by a retrieved page.')
    card = {'company_id': candidate_key(candidate['name'], domain), 'name': candidate['name'],
            'official_domain': domain or None, 'aliases': candidate.get('aliases', []),
            'sector': raw.get('sector') if raw.get('sector') in SECTORS else candidate['sector'],
            'description': clean(raw.get('description'), 350),
            'nj_presence': {'status': nj_status, 'location': clean(nj.get('location'), 150), 'evidence': nj_evidence},
            'signals': signals, 'public_interest_trend': 'not_measured',
            'limitations': list(dict.fromkeys([clean(v) for v in raw.get('uncertainties', []) if isinstance(v, str)] + warnings)),
            'follow_up_query': clean(raw.get('follow_up_query'), 250), 'provenance': 'public',
            'assessment_method': 'Gemini extraction; source/quote checks and ranking rules in code.'}
    rank_card(card)
    return card


def merge_assessments(previous, current):
    """A follow-up cannot silently erase earlier, verified evidence.

    Current versions of repeated event keys/quotes take precedence. Explicit new
    geographic conflicts remain visible. This is evidence accumulation, not a
    general contradiction resolver; inconsistent statements still need review.
    """
    current['signals'] = deduplicate(current['signals'] + previous['signals'])
    current['limitations'] = list(dict.fromkeys(previous['limitations'] + current['limitations']))
    if current['nj_presence']['status'] == 'unclear' and previous['nj_presence']['evidence']:
        current['nj_presence'] = previous['nj_presence']
    rank_card(current)
    return current


def rank_card(card):
    signals = card['signals']
    external = [s for s in signals if s['source_role'] in ('institution_confirmation', 'independent_reporting')
                and s['status'] in ('current', 'historical')]
    organizations = {norm(s['organization']) for s in external if s['organization']}
    families = {e['source_family'] for s in external for e in s['evidence']}
    events = {norm(s['event_key']) for s in external}
    substantial = [s for s in external if s['type'] in
                   ('technology_license', 'research_collaboration', 'industrial_partnership')
                   and s['status'] in ('current', 'historical')]
    recent = []
    for s in external:
        dated = parse_date(s.get('event_date'))
        if not dated:
            dated = next((parse_date(e.get('published_at')) for e in s['evidence'] if parse_date(e.get('published_at'))), None)
        if dated and 0 <= (date.today() - dated).days <= 730:
            recent.append(s)
    supported = card['nj_presence']['status'] in ('headquarters', 'operations')
    if not supported:
        level = 'outside_scope' if card['nj_presence']['status'] == 'outside_nj' else 'location_review'
    elif substantial and len(organizations) >= 2 and len(families) >= 2 and recent:
        level = 'stronger_evidence'
    elif len(organizations) >= 2 and len(families) >= 2 and recent:
        level = 'emerging_evidence'
    else:
        level = 'limited_evidence'
    card['assessment'] = level
    card['qualified'] = level in ('stronger_evidence', 'emerging_evidence')
    card['evidence_summary'] = {'external_organizations': len(organizations), 'source_families': len(families),
                                'distinct_event_labels': len(events), 'substantial_relationships': len(substantial),
                                'recent_signals': len(recent)}
    # Sorting key, not a 0–100 success probability. Kept out of public records.
    card['_rank'] = (card['qualified'], supported, min(len(substantial), 3), min(len(recent), 3),
                     min(len(organizations), 4), min(len(families), 3), min(len(events), 5))
    reason = {'stronger_evidence': 'Substantial outside involvement, multiple source families and recent activity.',
              'emerging_evidence': 'Recent recognition or participation across multiple source families.',
              'limited_evidence': 'Some sourced activity; breadth, depth or recency remains incomplete.',
              'location_review': 'Ecosystem evidence found; the NJ connection needs review.',
              'outside_scope': 'The retrieved evidence places this company outside the NJ scope.'}
    card['why_surfaced'] = reason[level]
    return card
