"""Offline regression tests; historical counts are fixture assertions only."""
import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare_shared_records as check

FIXTURE = json.loads((Path(__file__).parent / "fixtures/shared-records-20261014.json").read_text(encoding="utf-8"))


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.pages = copy.deepcopy(FIXTURE["pages"])
        self.original = check.extract(self.pages)

    def changed(self, filename, old, new):
        self.assertIn(old, self.pages[filename])
        self.pages[filename] = self.pages[filename].replace(old, new, 1)
        return check.compare(self.original, check.extract(self.pages))

    def test_historical_fixture_counts_and_hidden_identifiers(self):
        self.assertEqual(len(self.original["patents"]), 23)
        self.assertEqual(len(self.original["publications"]), 13)
        self.assertEqual(sum(p["status_ko"] == "등록" for p in self.original["patents"]), 11)
        self.assertEqual(self.original["patents"][9]["application"], "1020240011780")
        self.assertEqual(self.original["patents"][9]["publication"], "1020250017619")
        self.assertEqual(self.original["patents"][10]["registration"], "103029668")

    def test_bilingual_patent_title_preserves_original_comparison(self):
        title = self.original["patents"][0]["title"]
        bilingual = f'<span class="lang-ko">{title}</span><span class="lang-en">Display translation</span>'
        self.pages["ip.html"] = self.pages["ip.html"].replace(title, bilingual, 1)
        self.assertEqual(check.compare(self.original, check.extract(self.pages)), [])
        self.pages["ip.html"] = self.pages["ip.html"].replace(title, "수정된 원제목", 1)
        diffs = check.compare(self.original, check.extract(self.pages))
        self.assertEqual([d["field"] for d in diffs], ["patents[1].title"])
        self.assertEqual(diffs[0]["reference"], "수정된 원제목")

    def test_incomplete_or_ambiguous_bilingual_patent_title_fails(self):
        title = self.original["patents"][0]["title"]
        ko = f'<span class="lang-ko">{title}</span>'
        en = '<span class="lang-en">Display translation</span>'
        for markup in [ko, en, ko + ko + en, ko + en + en,
                       ko + '<span class="lang-en"></span>',
                       '<span class="lang-ko"></span>' + en]:
            with self.subTest(markup=markup):
                pages = copy.deepcopy(FIXTURE["pages"])
                pages["ip.html"] = pages["ip.html"].replace(title, markup, 1)
                with self.assertRaises(check.ExtractionError):
                    check.extract(pages)

    def test_r1_bilingual_heading_is_not_an_affiliation_value(self):
        block = check.Document(self.pages["people.html"]).root
        self.assertEqual(len(check.by_class(block, "lang-ko")), 2)
        self.assertEqual(self.original["center"], {"ko": "공정시스템연구센터", "en": "Process System Research Center"})
        self.pages["people.html"] = FIXTURE["reference_people"]
        self.assertEqual(check.extract(self.pages)["center"], self.original["center"])

    def test_center_changes_in_either_language_are_detected(self):
        for lang, before, after in [("ko", "공정시스템연구센터", "다른연구센터"),
                                    ("en", "Process System Research Center", "Process Systems Research Center")]:
            with self.subTest(lang=lang):
                pages = copy.deepcopy(FIXTURE["pages"])
                pages["people.html"] = pages["people.html"].replace(before, after)
                diffs = check.compare(self.original, check.extract(pages))
                self.assertEqual([d["field"] for d in diffs], [f"center.{lang}"])
                self.assertEqual(diffs[0]["reference"], after)

    def test_center_not_found_by_searching_current_literal_elsewhere(self):
        self.pages["people.html"] = self.pages["people.html"].replace("공정시스템연구센터", "새로운센터")
        self.pages["people.html"] += '<section>과거 경력: 공정시스템연구센터</section>'
        self.assertEqual(check.extract(self.pages)["center"]["ko"], "새로운센터")

    def test_duplicate_or_missing_center_values_fail_closed(self):
        for suffix in ['<span class="lang-ko">직위<br>다른센터</span>', '']:
            with self.subTest(suffix=suffix):
                pages = copy.deepcopy(FIXTURE["pages"])
                value = re.search(r'<span class="lang-ko">.*?</span>', pages["people.html"]).group()
                pages["people.html"] = pages["people.html"].replace(value, value + suffix if suffix else '')
                with self.assertRaises(check.ExtractionError):
                    check.extract(pages)

    def test_missing_center_line_is_not_an_empty_match(self):
        self.pages["people.html"] = self.pages["people.html"].replace('<br>공정시스템연구센터', '')
        with self.assertRaises(check.ExtractionError):
            check.extract(self.pages)

    def test_affiliation_source_whitespace_and_inline_formatting(self):
        self.pages['people.html'] = self.pages['people.html'].replace('선임연구원 · 한국화학연구원<br>',
            '\n <b>선임연구원</b> ·\n 한국화학연구원\n <br/>\n ')
        self.pages['people.html'] = self.pages['people.html'].replace('Process System Research Center',
            '\n PROCESS SYSTEM\n RESEARCH CENTER \n')
        self.pages['ip.html'] = self.pages['ip.html'].replace('>Granted<', '>GRANTED<')
        self.assertEqual(check.compare(self.original, check.extract(self.pages)), [])

    def test_heading_and_block_ambiguity_fail(self):
        for markup in ['', self.pages["people.html"] * 2]:
            with self.subTest(markup=markup[:30]):
                with self.assertRaises(check.ExtractionError):
                    check.extract_center(markup)

    def test_every_patent_field_change_is_reported(self):
        mutations = [
            ('class="no">1<', 'class="no">24<', 'patents[1].number'),
            ('비닐하우스 제설용 자동제설 로봇', '제목 정정', 'patents[1].title'),
            ('>등록<', '>심사중<', 'patents[1].status_ko'),
            ('>Granted<', '>Allowed<', 'patents[1].status_en'),
            ('10-1805184', '10-1805185', 'patents[1].registration'),
            ('data-application-number="10-2024-0011780"', 'data-application-number="10-2024-0011781"', 'patents[10].application'),
            ('data-publication-number="KR 10-2025-0017619"', 'data-publication-number="KR 10-2025-0017620"', 'patents[10].publication'),
            ('App. 10-2018-0098144', 'App. 10-2018-0098145', 'patents[12].application'),
            ('Pub. KR 10-2020-0022250', 'Pub. KR 10-2020-0022251', 'patents[12].publication'),
        ]
        for old, new, field in mutations:
            with self.subTest(field=field):
                self.pages = copy.deepcopy(FIXTURE["pages"])
                diffs = self.changed('ip.html', old, new)
                self.assertEqual([d['field'] for d in diffs], [field])

    def test_hidden_identifier_removal_and_attribute_registration(self):
        diffs = self.changed('ip.html', ' data-application-number="10-2024-0011780"', '')
        self.assertEqual(diffs[0]['field'], 'patents[10].application')
        self.assertIsNone(diffs[0]['reference'])
        self.pages = copy.deepcopy(FIXTURE['pages'])
        self.pages['ip.html'] = self.pages['ip.html'].replace('class="pubno">Reg. KR 10-1805184',
            'class="pubno" data-registration-number="KR 10-1805184">Reg. KR 10-1805184', 1)
        self.assertEqual(check.compare(self.original, check.extract(self.pages)), [])
        self.pages['ip.html'] = self.pages['ip.html'].replace('data-registration-number="KR 10-1805184"',
            'data-registration-number="KR 10-1805185"')
        with self.assertRaisesRegex(check.ExtractionError, 'conflicting registration'):
            check.extract(self.pages)

    def test_patent_missing_row_and_order_change(self):
        rows = re.findall(r'<tr><td class="no">.*?</tr>', self.pages['ip.html'], re.S)
        diffs = self.changed('ip.html', rows[0], '')
        self.assertIn('patents.count', [d['field'] for d in diffs])
        self.pages = copy.deepcopy(FIXTURE['pages'])
        self.pages['ip.html'] = self.pages['ip.html'].replace(rows[0], '__ROW__').replace(rows[1], rows[0]).replace('__ROW__', rows[1])
        diffs = check.compare(self.original, check.extract(self.pages))
        self.assertIn('patents[1].title', [d['field'] for d in diffs])
        self.assertIn('patents[1].number', [d['field'] for d in diffs])

    def test_publication_title_omission_and_order(self):
        items = re.findall(r'<article.*?</article>', self.pages['publications.html'], re.S)
        for changed in [self.pages['publications.html'].replace(items[0], ''),
                        self.pages['publications.html'].replace(items[0], '__A__').replace(items[1], items[0]).replace('__A__', items[1]),
                        self.pages['publications.html'].replace('Strategic Design', 'Different Design')]:
            with self.subTest(changed=changed[:70]):
                pages = copy.deepcopy(self.pages)
                pages['publications.html'] = changed
                self.assertTrue(check.compare(self.original, check.extract(pages)))

    def test_formatting_equivalence_and_ignored_content(self):
        self.pages['ip.html'] = self.pages['ip.html'].replace('Reg. KR 10-', 'Registration No.: KR 10–')
        self.pages['ip.html'] = self.pages['ip.html'].replace('<br>', ' / ').replace('Thermal systems', 'Different note')
        self.pages['publications.html'] = self.pages['publications.html'].replace('Strategic Design', 'Strategic\n  Design')
        self.pages['publications.html'] = self.pages['publications.html'].replace('<span class="pub-title">', '<p>Ignored authors</p><span class="pub-title">')
        self.pages['people.html'] = self.pages['people.html'].replace('선임연구원 · 한국화학연구원', 'Ignored role/institution')
        for page in self.pages:
            self.pages[page] = '<head><meta name="robots" content="noindex,follow"></head>' + self.pages[page] + '<aside>Different design and history</aside>'
        self.assertEqual(check.compare(self.original, check.extract(self.pages)), [])

    def test_same_future_records_do_not_fail_fixed_counts(self):
        new_row = '<tr><td class="no">24</td><td class="pubno">Reg. KR 10-9999999</td><td class="title">Synthetic test record</td><td><span class="status-pill"><span class="lang-ko">등록</span><span class="lang-en">Granted</span></span></td></tr>'
        self.pages['ip.html'] = self.pages['ip.html'].replace('</tbody>', new_row + '</tbody>')
        self.pages['publications.html'] = self.pages['publications.html'].replace('</div>', '<article class="publication-item"><span class="pub-title">Synthetic future paper</span></article></div>')
        records = check.extract(self.pages)
        self.assertEqual((len(records['patents']), len(records['publications'])), (24, 14))
        self.assertEqual(check.compare(records, copy.deepcopy(records)), [])

    def test_duplicate_numbers_ids_and_unreadable_display_fail(self):
        for before, after in [('class="no">2<', 'class="no">1<'), ('10-2429249', '10-1805184'),
                              ('Reg. KR 10-1805184', 'Unlabeled number 10-1805184')]:
            with self.subTest(before=before):
                pages = copy.deepcopy(FIXTURE['pages'])
                pages['ip.html'] = pages['ip.html'].replace(before, after, 1)
                with self.assertRaises(check.ExtractionError):
                    check.extract(pages)

    def test_empty_table_title_status_and_list_fail(self):
        mutations = [('ip.html', '<tbody>', '<tbody></tbody><tbody>'),
                     ('ip.html', '비닐하우스 제설용 자동제설 로봇', ''),
                     ('ip.html', 'class="lang-en">Granted', 'class="wrong">Granted'),
                     ('publications.html', 'class="publication-list"', 'class="wrong"')]
        for file, before, after in mutations:
            with self.subTest(file=file, before=before):
                pages = copy.deepcopy(FIXTURE['pages'])
                pages[file] = pages[file].replace(before, after, 1)
                with self.assertRaises(check.ExtractionError):
                    check.extract(pages)


class NetworkTests(unittest.TestCase):
    def test_bounded_retries_and_separate_access_failure(self):
        for error in [HTTPError('https://example.test', n, 'blocked', {}, None) for n in (403, 404, 429, 503)] + [URLError('DNS'), TimeoutError(), IncompleteRead(b'partial')]:
            with self.subTest(error=type(error).__name__):
                opener, sleep = Mock(side_effect=error), Mock()
                reader = check.GitHubReader(opener=opener, sleep=sleep)
                with self.assertRaisesRegex(check.RemoteUnavailable, 'after 3 attempts'):
                    reader.read('https://example.test')
                self.assertEqual(opener.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_retry_can_recover(self):
        opener = Mock(side_effect=[URLError('temporary'), io.BytesIO(b'valid')])
        self.assertEqual(check.GitHubReader(opener=opener, sleep=Mock()).read('https://example.test'), 'valid')
        self.assertEqual(opener.call_count, 2)

    def test_invalid_response_is_extraction_error(self):
        for body in [b'not-json', b'{}', b'{"sha":"main"}', b'{"sha":null}']:
            with self.subTest(body=body):
                reader = check.GitHubReader(opener=Mock(return_value=io.BytesIO(body)), sleep=Mock())
                with self.assertRaises(check.ExtractionError):
                    reader.resolve('example/repository')
        for body in [b'\xff', b'a' * 2_000_001]:
            with self.subTest(body_length=len(body)):
                with self.assertRaises(check.ExtractionError):
                    check.GitHubReader(opener=Mock(return_value=io.BytesIO(body))).read('https://example.test')

    def reader(self, mutation=None, failure=None):
        reader = Mock()
        shas = {repo: ('a' if side == 'official' else 'b') * 40 for side, repo in check.REPOSITORIES.items()}
        reader.resolve.side_effect = lambda repo: shas[repo]
        def page(repo, sha, filename):
            self.assertEqual(reader.resolve.call_count, 2, 'Both heads pinned before any HTML')
            self.assertEqual(sha, shas[repo])
            if failure and repo == check.REPOSITORIES['reference']:
                raise failure
            value = FIXTURE['pages'][filename]
            if repo == check.REPOSITORIES['reference'] and filename == 'people.html':
                value = FIXTURE['reference_people']
                if mutation:
                    value = value.replace('Process System Research Center', mutation)
            return value
        reader.page.side_effect = page
        return reader

    def test_heads_resolved_once_and_file_urls_pinned(self):
        reader = self.reader()
        result = check.online(reader)
        self.assertEqual(result['status'], 'MATCH')
        self.assertTrue(result['comparison_performed'])
        self.assertEqual(reader.resolve.call_count, 2)
        self.assertEqual(reader.page.call_count, 6)
        actual = check.GitHubReader()
        actual.read = Mock(return_value='source')
        actual.page('owner/repo', 'c' * 40, 'ip.html')
        actual.read.assert_called_once_with('https://raw.githubusercontent.com/owner/repo/' + 'c' * 40 + '/ip.html')

    def test_actual_mismatch_has_field_and_both_values(self):
        result = check.online(self.reader(mutation='Another Research Center'))
        self.assertEqual(result['status'], 'MISMATCH')
        self.assertEqual(result['differences'], [{'field': 'center.en', 'official': 'Process System Research Center', 'reference': 'Another Research Center'}])

    def test_access_and_extraction_are_not_reported_as_matches(self):
        for error, status in [(check.RemoteUnavailable('HTTP 429'), 'DEFERRED'),
                              (check.ExtractionError('value missing'), 'EXTRACTION_ERROR')]:
            with self.subTest(status=status):
                result = check.online(self.reader(failure=error))
                self.assertEqual(result['status'], status)
                self.assertFalse(result['comparison_performed'])
                self.assertEqual(result['differences'], [])
                self.assertEqual(result['sources']['reference']['sha'], 'b' * 40)

    def test_unresolved_head_is_explicit_and_other_sha_is_retained(self):
        reader = self.reader()
        reader.resolve.side_effect = [check.RemoteUnavailable('HTTP 403'), 'b' * 40]
        result = check.online(reader)
        self.assertEqual(result['status'], 'DEFERRED')
        self.assertIsNone(result['sources']['official']['sha'])
        self.assertEqual(result['sources']['reference']['sha'], 'b' * 40)
        self.assertEqual(reader.resolve.call_count, 2)

    def test_cli_reports_and_exit_codes(self):
        for result in [check.online(self.reader()), check.online(self.reader(mutation='Different Center')),
                       check.online(self.reader(failure=check.RemoteUnavailable('offline'))),
                       check.online(self.reader(failure=check.ExtractionError('bad markup')))]:
            with self.subTest(status=result['status']), tempfile.TemporaryDirectory() as tmp:
                output, summary = Path(tmp) / 'result.json', Path(tmp) / 'summary.md'
                log = io.StringIO()
                with patch.object(check, 'online', return_value=result), contextlib.redirect_stdout(log):
                    code = check.main(['online', '--output', str(output), '--summary', str(summary)])
                self.assertEqual(code, check.EXIT_CODES[result['status']])
                self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['status'], result['status'])
                for text in (log.getvalue(), summary.read_text(encoding='utf-8')):
                    self.assertIn(result['status'], text)
                    self.assertIn('a' * 40, text)
                    self.assertIn('b' * 40, text)

    def test_extract_cli_is_offline_and_accepts_actual_changed_center(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, html in FIXTURE['pages'].items():
                (Path(tmp) / name).write_text(html.replace('공정시스템연구센터', '가상검사용센터'), encoding='utf-8')
            with patch.object(check, 'GitHubReader', side_effect=AssertionError('network forbidden')), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(['extract', '--root', tmp]), 0)


class WorkflowTests(unittest.TestCase):
    def test_network_workflow_is_not_a_pr_check(self):
        root = Path(__file__).resolve().parents[2]
        online = (root / '.github/workflows/compare-shared-records.yml').read_text(encoding='utf-8')
        self.assertIn("cron: '17 0 * * 1'", online)
        self.assertIn('workflow_dispatch:', online)
        self.assertNotIn('pull_request:', online)
        self.assertNotIn('push:', online)
        self.assertNotIn('continue-on-error', online)
        self.assertIn('contents: read', online)
        self.assertNotIn(': write', online)
        self.assertIn('if: always()', online)
        validation = (root / '.github/workflows/validate-public-site.yml').read_text(encoding='utf-8')
        for command in ['python tools/validate_public_site.py', 'node --check assets/site.js',
                        'python -B -m unittest discover', 'python -B tools/compare_shared_records.py extract']:
            self.assertIn(command, validation)
        self.assertNotIn('compare_shared_records.py online', validation)


if __name__ == '__main__':
    unittest.main()
