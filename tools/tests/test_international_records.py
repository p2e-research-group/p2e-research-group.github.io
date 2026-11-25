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
        self.assertEqual(data[11]['registration'], '103040665')
        self.assertEqual([r['status_en'] for r in data], ['Granted'] * 12 + ['Published'] * 11)
        expected_apps = ['1020240108551', '1020180098144', '1020200096553',
                         '1020220161616', '1020230042123', '1020230052876',
                         '1020230127347', '1020240032733']
        self.assertEqual([r['application'] for r in data[11:19]], expected_apps)
        for publication, parent in [('WO2026038778A1', '12'), ('WO2024117507A1', '15'),
                                    ('WO2025188145A1', '19')]:
            self.assertEqual(next(r for r in self.original if r['publication'] == publication)['parent'], parent)

    def test_renumbering_preserves_existing_invention_bookmarks(self):
        root = check.Document(self.source).root
        for old, current in [(19, 12), *[(n, n + 1) for n in range(12, 19)]]:
            row = check.one((e for e in root.elements() if e.attrs.get('id') == f'patent-{old}'), 'bookmark')
            self.assertEqual(check.one(check.by_class(row, 'no'), 'number').text(), str(current))
        data = build.load_data(ROOT)
        self.assertEqual(build.render(self.source, data), self.source)

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
        for old,new in [('>US11674720B2</a>','>US99999999B2</a>'),('class="ip-stage granted"><span class="lang-en">Granted', 'class="ip-stage granted"><span class="lang-en">Published')]:
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
        self.assertEqual(check.extract_records(fixture['pages'])['linked_patents'],[])

if __name__ == '__main__':
    unittest.main()
