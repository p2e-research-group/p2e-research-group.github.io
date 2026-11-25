"""Offline domestic href regressions: identity, strict extraction and cross-site drift."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare_shared_records as check

GOOGLE_GRANT = 'https://patents.google.com/patent/KR103029668B1/ko'
GOOGLE_PUBLICATION = 'https://patents.google.com/patent/KR20220017011A/ko'
KIPRIS_GRANT = 'https://doi.org/10.8080/1020240041982'
KIPRIS_PUBLICATION = 'https://doi.org/10.8080/1020200096553'
GRANT = 'Reg. KR 10-3029668'
PUBLICATION = 'App. 10-2020-0096553<br>Pub. KR 10-2022-0017011'


def anchor(text, url):
    return f'<a class="ip-domestic-source" href="{url}">{text}</a>'


def page(grant_link=None, publication_link=None):
    grant = anchor(GRANT, KIPRIS_GRANT) if grant_link is None else grant_link
    pub = anchor(PUBLICATION, GOOGLE_PUBLICATION) if publication_link is None else publication_link
    return f'''<table class="registry-table"><tbody>
    <tr><td class="no">1</td><td class="pubno" data-application-number="10-2024-0041982"
      data-publication-number="KR 10-2025-0144764">{grant}</td><td class="title">Grant</td>
      <td><span class="status-pill"><span class="lang-ko">등록</span><span class="lang-en">Granted</span></span></td></tr>
    <tr><td class="no">2</td><td class="pubno">{pub}</td><td class="title">Publication</td>
      <td><span class="status-pill"><span class="lang-ko">공개</span><span class="lang-en">Published</span></span></td></tr>
    </tbody></table>'''


def pages(ip):
    return {'ip.html': ip,
            'publications.html': '<div class="publication-list"><article class="publication-item"><span class="pub-title">Paper</span></article></div>',
            'people.html': '<div class="profile-facts"><div class="profile-fact"><b>현재 소속</b><span class="lang-ko">직위<br>센터</span><span class="lang-en">Role<br>Center</span></div></div>',
            'data/ip-portfolio.json': '{}'}


def run_online(left, right):
    # Only the unrelated portfolio is stubbed; real extract()/compare()/online()
    # and the domestic HTML parser execute normally with no network.
    snapshots = {'official': pages(left), 'reference': pages(right)}
    by_repo = {repo: snapshots[side] for side, repo in check.REPOSITORIES.items()}
    reader = Mock()
    reader.resolve.side_effect = lambda repo: ('a' if repo == check.REPOSITORIES['official'] else 'b') * 40
    reader.page.side_effect = lambda repo, sha, filename: by_repo[repo][filename]
    with patch.object(check, 'extract_portfolio', return_value={'areas': [], 'technology_transfers': []}):
        return check.online(reader)


class DomesticLinkTests(unittest.TestCase):
    def test_both_providers_and_both_record_types(self):
        for grant in (GOOGLE_GRANT, KIPRIS_GRANT):
            for pub in (GOOGLE_PUBLICATION, KIPRIS_PUBLICATION):
                with self.subTest(grant=grant, publication=pub):
                    ip = page(anchor(GRANT, grant), anchor(PUBLICATION, pub))
                    records = check.extract_patents(ip)
                    self.assertEqual([r['domestic_source_url'] for r in records], [grant, pub])
                    result = run_online(ip, ip)
                    self.assertEqual(result['status'], 'MATCH')
                    self.assertTrue(result['comparison_performed'])
                    self.assertEqual(result['sources']['official']['records']['patents'], records)

    def test_missing_duplicate_or_partial_anchor_fails_closed(self):
        good = anchor(PUBLICATION, GOOGLE_PUBLICATION)
        bad = [PUBLICATION, good.replace(f' href="{GOOGLE_PUBLICATION}"', ''),
               anchor(PUBLICATION, ''), good.replace('ip-domestic-source', 'other'),
               good + anchor('', GOOGLE_PUBLICATION),
               'App. 10-2020-0096553<br>' + anchor('Pub. KR 10-2022-0017011', GOOGLE_PUBLICATION),
               good.replace('<a ', '<span ').replace('</a>', '</span>')]
        for markup in bad:
            with self.subTest(markup=markup), self.assertRaisesRegex(check.ExtractionError, 'domestic source'):
                check.extract_patents(page(publication_link=markup))

    def test_wrong_google_and_kipris_targets_and_malformed_urls(self):
        for url in (GOOGLE_GRANT.replace('3029668', '3040665'),
                    'https://patents.google.com/patent/KR20250144764A/ko',
                    GOOGLE_GRANT.replace('B1', 'A'), KIPRIS_PUBLICATION,
                    'http' + GOOGLE_GRANT[5:], GOOGLE_GRANT + '?x=1',
                    GOOGLE_GRANT + '#fragment', GOOGLE_GRANT.replace('google.com', 'google.com.invalid'),
                    GOOGLE_GRANT.replace('/ko', '/en'), ' ' + GOOGLE_GRANT):
            with self.subTest(url=url), self.assertRaises(check.ExtractionError):
                check.extract_patents(page(grant_link=anchor(GRANT, url)))
        for url in (GOOGLE_GRANT, GOOGLE_PUBLICATION.replace('17011', '17012'), KIPRIS_GRANT):
            with self.subTest(url=url), self.assertRaises(check.ExtractionError):
                check.extract_patents(page(publication_link=anchor(PUBLICATION, url)))
        no_application = page().replace(' data-application-number="10-2024-0041982"', '')
        with self.assertRaisesRegex(check.ExtractionError, 'KIPRIS application mismatch'):
            check.extract_patents(no_application)

    def test_locally_valid_provider_change_is_exact_cross_site_mismatch(self):
        left = page()
        right = page(grant_link=anchor(GRANT, GOOGLE_GRANT))
        result = run_online(left, right)
        self.assertEqual(result['status'], 'MISMATCH')
        self.assertTrue(result['comparison_performed'])
        self.assertEqual(result['differences'], [{'field': 'patents[1].domestic_source_url',
                                                'official': KIPRIS_GRANT, 'reference': GOOGLE_GRANT}])
        records = {'patents': check.extract_patents(left), 'center': {'ko': '센터', 'en': 'Center'}}
        altered = copy.deepcopy(records)
        altered['patents'][0]['domestic_source_url'] += ' '
        self.assertEqual(check.compare(records, altered)[0]['field'], 'patents[1].domestic_source_url')

    def test_full_pipeline_rejects_missing_or_wrong_link_even_on_both_sites(self):
        valid = page()
        href = f'href="{KIPRIS_GRANT}"'
        wrong_href = f'HREF="{KIPRIS_PUBLICATION}"'
        invalid_pages = [page(grant_link=GRANT), page(grant_link=anchor(GRANT, KIPRIS_PUBLICATION)),
                         valid.replace(href, f'{wrong_href} {href}', 1),
                         valid.replace(href, f'{href} {wrong_href}', 1),
                         valid.replace(href, f'{href} {href}', 1)]
        for invalid in invalid_pages:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(check.ExtractionError, 'domestic source|KIPRIS application'):
                    check.extract(pages(invalid))
            for left, right, sources in ((valid, invalid, ['reference']),
                                          (invalid, valid, ['official']),
                                          (invalid, invalid, ['official', 'reference'])):
                with self.subTest(sources=sources, invalid=invalid):
                    result = run_online(left, right)
                    self.assertEqual(result['status'], 'EXTRACTION_ERROR')
                    self.assertFalse(result['comparison_performed'])
                    self.assertEqual(result['differences'], [])
                    self.assertEqual([e['source'] for e in result['errors']], sources)
                    self.assertTrue(all('domestic source' in e['message'] or 'KIPRIS application' in e['message']
                                        for e in result['errors']))

    def test_legacy_scope_only_preserves_historical_linkless_fixture(self):
        old = page(grant_link=GRANT, publication_link=PUBLICATION)
        self.assertNotIn('domestic_source_url', check.extract_records(pages(old))['patents'][0])
        with self.assertRaises(check.ExtractionError):
            check.extract(pages(old))


if __name__ == '__main__':
    unittest.main()
