#!/usr/bin/env python3
"""Conservative, offline rules baseline for supplied person/company candidates.

Reads snapshots, never reference evidence or labels. This is a development-set
baseline, not entity discovery, identity verification, or a general NLP system.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'benchmark'
# Order matters: prefer specific roles to generic board language at the same offset.
ROLE = re.compile(
    r'(?P<observer>(?:board observer|observer on the boards?|observer) (?:for|of)\s*|observer on the boards? of\s*)'
    r'|(?P<investment>led(?: or co-led)? investments? in\s*)'
    r'|(?P<director>director (?:on the board )?of\s*)'
    r'|(?P<board>(?:on the board of|sits on several boards, including,?|served on the board of numerous private and public companies, including)\s*)',
    re.I,
)
UNCERTAIN = re.compile(r'\b(?:not|never|denied|rumou?r|might|may|could|would|reportedly)\b', re.I)


def mentions(text, name):
    return re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.I) is not None


def extract(text, person, company, person_aliases=(), company_aliases=()):
    """Return literal paragraph evidence with offsets; abstain outside narrow rules."""
    names = [person, *person_aliases]
    companies = [company, *company_aliases]
    heading = None
    found = []
    for block in re.finditer(r'\S[^\n]*(?:\n(?!\s*\n)[^\n]+)*', text):
        paragraph = block.group()
        if paragraph.startswith('#'):
            # A subordinate job-title heading must not erase a person's heading.
            if re.match(r'#{1,2}\s', paragraph):
                heading = paragraph.lstrip('# ').strip()
            continue
        clean = paragraph.replace('*', '')
        explicit = any(re.match(r'^' + re.escape(name) + r'(?!\w)', clean, re.I) for name in names)
        in_section = heading is not None and any(heading.casefold() == n.casefold() for n in names)
        if paragraph.startswith('|') or (not explicit and not in_section):
            continue
        # Full-name attribution in a block must precede the relationship claim.
        # Only accept clauses with an explicit subject or a tightly scoped pronoun.
        first_names = {n.split()[0] for n in names}
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])', clean):
            if UNCERTAIN.search(sentence):
                continue
            subject = re.match(r'^(?:Before [^,]+,\s*)?(?:' + '|'.join(re.escape(n) for n in sorted(names + list(first_names), key=len, reverse=True)) + r'|He|She)\b', sentence)
            if not subject:
                continue
            if not in_section and not any(mentions(clean[:clean.find(sentence) + len(sentence)], n) for n in names):
                continue
            matches = list(ROLE.finditer(sentence))
            for i, role in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(sentence)
                objects = sentence[role.end():end]
                # Stop at a new independent subject or verb, so unrelated clauses
                # do not inherit the preceding role.
                objects = re.split(r';|\b(?:but|where|while|who|he|she|works|joined|invested)\b', objects, flags=re.I)[0]
                if not any(mentions(objects, c) for c in companies):
                    continue
                kind = role.lastgroup
                historical = bool(re.search(r'\b(?:was|has served|served)\b', sentence[:role.end()], re.I))
                label = {'observer': 'board_observer', 'investment': 'led_or_coled_investment', 'director': 'director', 'board': 'board_member'}[kind]
                if historical and kind in ('director', 'board'):
                    label = 'historical_director' if kind == 'director' else 'historical_board_member'
                found.append({'relationship': label, 'quote': paragraph,
                              'start_offset': block.start(), 'end_offset': block.end(),
                              'relationship_start': None, 'relationship_end': None})
    return [dict(items) for items in dict.fromkeys(tuple(item.items()) for item in found)]


def load_sources(base=BASE):
    sources = json.loads((base / 'sources.json').read_text())
    for source in sources:
        path = (base / source['snapshot_path']).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ValueError('Snapshot path escapes benchmark')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            raise ValueError('Snapshot hash mismatch: ' + source['id'])
        source['text'] = data.decode('utf-8')
    return sources


def collect(candidate, sources):
    evidence = []
    for source in sources:
        for match in extract(source['text'], candidate['person'], candidate['company'],
                             candidate.get('person_aliases', []), candidate.get('company_aliases', [])):
            evidence.append({**match, 'source_id': source['id'], 'url': source['url'],
                             'snapshot_sha256': source['sha256'], 'first_observed_at': source['retrieved_at']})
    roles = sorted({e['relationship'] for e in evidence})
    conflict = 'board_observer' in roles and any(r in roles for r in ('director', 'board_member', 'historical_director', 'historical_board_member'))
    return {'person': candidate['person'], 'company': candidate['company'],
            'status': 'review_role_conflict' if conflict else ('supported' if evidence else 'abstain'),
            'roles': roles, 'relationship_start': None, 'relationship_end': None,
            'first_public_date': None, 'early_stage_verified': False,
            'evidence': evidence,
            'limitations': ['Rule baseline: supplied identities are not independently verified.',
                            'Dates and stage are not extracted; metadata never supplies relationship dates.',
                            'Source count does not establish independent corroboration.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--person', required=True)
    parser.add_argument('--company', required=True)
    parser.add_argument('--person-alias', action='append', default=[])
    parser.add_argument('--company-alias', action='append', default=[])
    args = parser.parse_args()
    result = collect({'person': args.person, 'company': args.company,
                      'person_aliases': args.person_alias, 'company_aliases': args.company_alias}, load_sources())
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
