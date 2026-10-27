"""High-value regressions for linked public international records."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import compare_shared_records as check
import build_ip_portfolio as build

class InternationalRecordsTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'ip.html').read_text(encoding='utf-8')
        self.original = check.extract_linked_patents(self.source)

    def test_grants_publications_and_pct_are_counted_separately(self):
        self.assertEqual(len(self.original), 16)
        self.assertEqual(sum(r['stage'] == 'granted' for r in self.original), 5)
        self.assertEqual(sum(r['stage'] == 'pct_published' for r in self.original), 6)
        self.assertEqual(sum(r['stage'] in ('published','allowed') for r in self.original), 5)
        self.assertEqual(next(r for r in self.original if r['publication']=='JP7664667B2')['parent'], '8')

    def test_domestic_record_numbers_order_and_registered_titles_survive(self):
        data = check.extract_patents(self.source)
        self.assertEqual([r['number'] for r in data], list(range(1,24)))
        self.assertEqual(data[10]['registration'], '103029668')

    def test_missing_and_changed_foreign_record_are_detected(self):
        old = dict(patents=[],linked_patents=self.original,publications=[],center={'ko':'x','en':'x'})
        new = copy.deepcopy(old)
        new['linked_patents'].pop()
        self.assertTrue(check.compare(old,new))
        new = copy.deepcopy(old)
        new['linked_patents'][0]['evidence_url'] += '?changed'
        self.assertTrue(check.compare(old,new))

    def test_foreign_record_cannot_move_to_another_domestic_parent(self):
        changed=self.source.replace('data-parent="2"','data-parent="3"',1)
        with self.assertRaises(check.ExtractionError):
            check.extract_linked_patents(changed)

    def test_pct_cannot_be_reclassified_as_a_grant(self):
        changed=self.source.replace('data-stage="pct_published"','data-stage="granted"',1)
        with self.assertRaises(check.ExtractionError):
            check.extract_linked_patents(changed)

    def test_visible_identifiers_and_statuses_cannot_disagree_with_data(self):
        for old,new in [('>US11674720B2</a>','>US99999999B2</a>'),('>등록공보</span>','>공개</span>')]:
            with self.subTest(old=old), self.assertRaises(check.ExtractionError):
                check.extract_linked_patents(self.source.replace(old,new,1))

    def test_duplicate_application_is_rejected(self):
        item=next(iter(check.by_class(check.Document(self.source).root,'ip-linked-record')))
        start=self.source.index('<li class="ip-linked-record"')
        end=self.source.index('</li>',start)+5
        changed=self.source[:end]+self.source[start:end]+self.source[end:]
        with self.assertRaises(check.ExtractionError):
            check.extract_linked_patents(changed)

    def test_static_render_is_idempotent_and_data_drift_is_detected(self):
        data=build.load_data(ROOT)
        self.assertEqual(build.render(self.source,data),self.source)
        data['records'][0]['publication']='US99999999B2'
        self.assertNotEqual(build.render(self.source,data),self.source)

    def test_historical_html_without_foreign_records_still_extracts(self):
        fixture=json.loads((ROOT/'tools/tests/fixtures/shared-records-20261014.json').read_text())
        self.assertEqual(check.extract(fixture['pages'])['linked_patents'],[])

if __name__ == '__main__':
    unittest.main()
