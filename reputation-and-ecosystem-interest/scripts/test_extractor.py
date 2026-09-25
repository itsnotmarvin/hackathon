#!/usr/bin/env python3
"""Failure-oriented regression checks for the narrow offline baseline."""
import unittest
from extract_relationships import collect, extract, load_sources


class ExtractorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_sources()

    def test_no_cross_person_attribution(self):
        result = collect({'person': 'Jennifer Solomon', 'company': 'BigCommerce'}, self.sources)
        self.assertEqual(result['status'], 'abstain')

    def test_conflicting_roles_preserved(self):
        result = collect({'person': 'Stephen Socolof', 'person_aliases': ['Steve Socolof', 'Stephen J. Socolof'], 'company': 'Kintra Fibers'}, self.sources)
        self.assertEqual(result['status'], 'review_role_conflict')
        self.assertEqual(result['roles'], ['board_member', 'board_observer'])

    def test_metadata_not_appointment_date(self):
        result = collect({'person': 'Vaughn Crowe', 'company': 'Toothio'}, self.sources)
        self.assertEqual(result['status'], 'supported')
        self.assertIsNone(result['relationship_start'])
        self.assertIsNone(result['first_public_date'])

    def test_investment_not_seed_stage(self):
        result = collect({'person': 'Dan Borok', 'company': 'BigCommerce'}, self.sources)
        self.assertEqual(result['status'], 'supported')
        self.assertFalse(result['early_stage_verified'])

    def test_role_boundaries(self):
        text = '## Alice Smith\n\nShe is a director of Example One and board observer for Example Two.'
        self.assertEqual(extract(text, 'Alice Smith', 'Example Two')[0]['relationship'], 'board_observer')
        self.assertEqual(extract(text, 'Alice Smith', 'Example One')[0]['relationship'], 'director')

    def test_negation_uncertainty_and_name_substrings(self):
        for body in ['She is not a director of Example.', 'She might be a director of Example.', 'She is a director of ExampleTwo.']:
            self.assertEqual(extract('## Alice Smith\n\n' + body, 'Alice Smith', 'Example'), [])

    def test_multi_person_table_abstains(self):
        self.assertEqual(extract('| Alice Smith | Bob Jones is a director of Example. |', 'Alice Smith', 'Example'), [])

    def test_literal_evidence_offsets(self):
        for source in self.sources:
            for item in extract(source['text'], 'Dan Borok', 'BigCommerce'):
                self.assertEqual(source['text'][item['start_offset']:item['end_offset']], item['quote'])


if __name__ == '__main__':
    unittest.main()
