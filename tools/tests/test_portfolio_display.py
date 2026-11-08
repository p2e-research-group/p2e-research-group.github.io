"""Small display regressions using the accepted four-area source and static HTML."""
import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from html import escape
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_ip_portfolio as build
import compare_shared_records as check

EXPECTED_AREAS = [
    ('diffusion-cooling', '냉난방·축열 시스템', 'Heating, Cooling & Thermal Storage', [2, 5, 7, 12]),
    ('co2-reactor', '광에너지 변환·활용', 'Light-Energy Conversion & Utilization', [3, 8]),
    ('hydrogen-electrolysis', '수소·수전해 전극 및 촉매', 'Hydrogen & Water-Electrolysis Catalysts',
     [10, 11, 14, 18, 20, 21, 22, 23]),
    ('industrial-systems', '탄소·연료·해양 공정', 'Carbon, Fuel & Offshore Processes', [9, 15, 16, 17, 19]),
]


class PortfolioDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {name: (ROOT / name).read_text(encoding='utf-8') for name in check.FILES}
        cls.source = cls.pages['ip.html']
        cls.data = json.loads(cls.pages['data/ip-portfolio.json'])
        cls.records = check.extract(cls.pages)
        cls.note = re.search(r'<div class="ip-transfer-record".*?</div>', cls.source).group()

    def display(self, source=None, data=None):
        return check.extract_portfolio(self.source if source is None else source,
                                       json.dumps(self.data if data is None else data, ensure_ascii=False))

    def rendered_records(self, data):
        pages = dict(self.pages)
        pages['data/ip-portfolio.json'] = json.dumps(data, ensure_ascii=False)
        pages['ip.html'] = build.render(self.source, data)
        return check.extract(pages)

    def test_accepted_names_order_members_and_understated_note(self):
        portfolio = self.records['portfolio']
        expected = [{'id': i, 'label_ko': check.normalize(ko), 'label_en': check.normalize(en), 'patents': members}
                    for i, ko, en, members in EXPECTED_AREAS]
        self.assertEqual(portfolio['areas'], expected)
        self.assertEqual(portfolio['technology_transfers'],
                         [{'parent': 1, 'label_ko': '기술이전: 어밸브', 'label_en': 'Technology transfer: AVALVE'}])
        self.assertEqual(check.compare(self.records, copy.deepcopy(self.records)), [])

    def test_area_text_or_json_only_edits_fail_before_comparison(self):
        for card in self.data['cards']:
            for lang in ('ko', 'en'):
                with self.subTest(area=card['id'], lang=lang):
                    changed = self.source.replace('>' + escape(card[lang]) + '</span>', '>Changed area</span>', 1)
                    self.assertTrue(changed != self.source, 'test mutation must change the displayed heading')
                    with self.assertRaisesRegex(check.ExtractionError, 'data/HTML conflict'):
                        self.display(changed)
                    data = copy.deepcopy(self.data)
                    next(c for c in data['cards'] if c['id'] == card['id'])[lang] += ' changed'
                    with self.assertRaisesRegex(check.ExtractionError, 'data/HTML conflict'):
                        self.display(data=data)

    def test_membership_missing_duplicate_moved_reordered_and_broken_links_fail(self):
        member = re.search(r'<li class="ip-portfolio-invention.*?</li>', self.source).group()
        changes = [self.source.replace(member, '', 1), self.source.replace(member, member * 2, 1),
                   self.source.replace('href="#patent-2"', 'href="#patent-3"', 1),
                   self.source.replace('href="#patent-2"', 'href="#patent-999"', 1),
                   self.source.replace('id="patent-2"', 'id="broken-patent-2"', 1),
                   self.source.replace('>특허 2</span>', '>특허 3</span>', 1)]
        for changed in changes:
            with self.subTest(change=changes.index(changed)), self.assertRaises(check.ExtractionError):
                self.display(changed)
        for parents in ([5, 2, 7, 12], [2, 2, 7, 12], [True, 5, 7, 12], [999, 5, 7, 12]):
            data = copy.deepcopy(self.data)
            data['cards'][0]['parents'] = parents
            with self.subTest(parents=parents), self.assertRaises(check.ExtractionError):
                self.display(data=data)

    def test_missing_extra_or_detached_areas_and_invalid_data_fail(self):
        for data in ({}, [], {'cards': [], 'technology_transfers': []},
                     {**self.data, 'cards': self.data['cards'] * 2},
                     {**self.data, 'technology_transfers': []},
                     {**self.data, 'technology_transfers': [{'parent': True}]}):
            with self.subTest(data=str(data)[:50]), self.assertRaises(check.ExtractionError):
                self.display(data=data)
        for changed in (self.source.replace('class="family-card"', 'class="lost-card"', 1),
                        self.source.replace('class="family-grid"', 'class="lost-grid"', 1),
                        self.source.replace('id="families"', 'id="lost-families"', 1)):
            with self.subTest(changed=changed[:40]), self.assertRaises(check.ExtractionError):
                self.display(changed)
        with self.assertRaises(check.ExtractionError):
            check.extract_portfolio(self.source, '{not JSON')

    def test_transfer_text_language_removal_duplication_and_banner_fail(self):
        for note in ('', self.note * 2, self.note.replace('어밸브', '다른기업'),
                     self.note.replace('AVALVE', 'OTHER'), self.note.replace('lang-en', 'lost-language'),
                     self.note.replace('ip-transfer-record', 'ip-transfer-record ip-badge'),
                     self.note.replace('data-transfer-parent="1"', 'data-transfer-parent="2"'),
                     self.note.replace('</div>', ' Additional transfer claim</div>'),
                     self.note.replace('class="lang-ko"', 'class="lang-ko" hidden'),
                     self.note + '<section>기술이전: 어밸브</section>'):
            with self.subTest(note=note[:100]), self.assertRaises(check.ExtractionError):
                self.display(self.source.replace(self.note, note, 1))

    def test_transfer_cannot_leave_parent_supplement_or_become_legal_status(self):
        removed = self.source.replace(self.note, '', 1)
        row2 = re.search(r'<tr role="row" id="patent-2".*?</tr>', removed).group()
        moved = removed.replace(row2, row2.replace('</td></tr>', self.note + '</td></tr>'), 1)
        status = removed.replace('<span class="status-pill">', '<span class="status-pill">' + self.note, 1)
        for changed in (removed + self.note, moved, status):
            with self.subTest(changed=changed[-60:]), self.assertRaises(check.ExtractionError):
                self.display(changed)

    def test_consistent_data_and_html_changes_report_exact_cross_site_fields(self):
        data = copy.deepcopy(self.data)
        data['cards'][0]['ko'] = '변경된 분야'
        data['cards'][0]['parents'][0], data['cards'][1]['parents'][0] = 3, 2
        data['technology_transfers'][0]['recipient_en'] = 'OTHER'
        changed = self.rendered_records(data)
        diffs = check.compare(self.records, changed)
        self.assertEqual({d['field'] for d in diffs},
                         {'portfolio.areas[1].label_ko', 'portfolio.areas[1].patents[1]',
                          'portfolio.areas[2].patents[1]', 'portfolio.technology_transfers[1].label_en'})
        transfer = next(d for d in diffs if d['field'].endswith('.label_en'))
        self.assertEqual((transfer['official'], transfer['reference']),
                         ('Technology transfer: AVALVE', 'Technology transfer: OTHER'))

    def test_formatting_and_noncontract_descriptions_do_not_create_false_drift(self):
        changed = self.source.replace('Heating, Cooling &amp; Thermal Storage',
                                      'Heating,\n Cooling &amp; Thermal Storage')
        changed = changed.replace('class="ip-transfer-record" data-transfer-parent="1"',
                                  "data-transfer-parent='1' class='ip-transfer-record'")
        changed = changed.replace(self.data['cards'][0]['description_en'], 'Updated explanatory prose')
        self.assertEqual(self.display(changed), self.records['portfolio'])

    def test_online_pins_json_and_html_and_does_not_skip_bad_display(self):
        data = copy.deepcopy(self.data)
        data['cards'][0]['en'] += ' changed'
        changed = dict(self.pages, **{'ip.html': build.render(self.source, data),
                                    'data/ip-portfolio.json': json.dumps(data)})
        calls = []
        reader = Mock()
        reader.resolve.side_effect = lambda repo: ('a' if repo == check.REPOSITORIES['official'] else 'b') * 40
        def page(repo, sha, name):
            self.assertEqual(reader.resolve.call_count, 2)
            self.assertEqual(sha, ('a' if repo == check.REPOSITORIES['official'] else 'b') * 40)
            calls.append((repo, sha, name))
            return (self.pages if repo == check.REPOSITORIES['official'] else changed)[name]
        reader.page.side_effect = page
        result = check.online(reader)
        self.assertEqual(result['status'], 'MISMATCH')
        self.assertEqual(result['differences'][0]['field'], 'portfolio.areas[1].label_en')
        self.assertEqual(len(calls), 2 * len(check.FILES))
        self.assertEqual(result['sources']['official']['counts']['portfolio_areas'], 4)
        changed['ip.html'] = self.source
        reader.reset_mock()
        result = check.online(reader)
        self.assertEqual(result['status'], 'EXTRACTION_ERROR')
        self.assertFalse(result['comparison_performed'])

    def test_missing_portfolio_input_fails_offline_cli_with_saved_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in self.pages.items():
                if name.endswith('.html'):
                    (root / name).write_text(value, encoding='utf-8')
            output = root / 'result.json'
            with (patch.object(check, 'GitHubReader', side_effect=AssertionError('network forbidden')),
                  contextlib.redirect_stdout(io.StringIO())):
                code = check.main(['extract', '--root', tmp, '--output', str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.read_text())['status'], 'EXTRACTION_ERROR')


if __name__ == '__main__':
    unittest.main()
