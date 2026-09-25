#!/usr/bin/env python3
"""Development-set evaluation: candidate names supplied, reference labels withheld."""
import json
from extract_relationships import BASE, collect, load_sources


def main():
    sources = load_sources()
    cases = json.loads((BASE / 'cases.json').read_text())
    results = []
    for case in cases:
        # Do not pass gold source IDs, quotations, roles, dates, or limitations.
        candidate = {k: case[k] for k in ('person', 'company', 'person_aliases', 'company_aliases')}
        result = collect(candidate, sources)
        results.append({'case_id': case['id'], 'reference_relationship': case['relationship'], **result})
    output = {'evaluation': 'Unblinded development set; supplied identity pairs, all snapshots searched. Not discovery recall or held-out accuracy.',
              'supported_pairs': sum(r['status'] == 'supported' for r in results),
              'abstained_pairs': sum(r['status'] == 'abstain' for r in results),
              'total_pairs': len(results), 'results': results}
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
