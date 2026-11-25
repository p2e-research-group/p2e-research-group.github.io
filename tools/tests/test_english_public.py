"""Regression coverage for the English public site versus the bilingual reference."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import compare_shared_records as check
from validate_public_site import PageParser


class EnglishPublicTests(unittest.TestCase):
    def test_provenance_is_not_ui_text_but_visible_copy_and_controls_are(self):
        def parse(body):
            parser = PageParser()
            parser.feed('<html lang="en"><body data-lang="en">' + body + '</body></html>')
            return parser
        page = parse('<p data-original-title-ko="발명">Invention</p>')
        self.assertFalse(page.korean_ui or page.language_controls)
        self.assertTrue(parse('<p>발명</p>').korean_ui)
        self.assertTrue(parse('<img alt="그림" src="item.svg">').korean_ui)
        self.assertTrue(parse('<button data-lang-button="ko">KO</button>').language_controls)

    def test_shared_patents_require_original_and_compare_both_titles(self):
        official_ip = (ROOT / 'ip.html').read_text(encoding='utf-8')
        left = check.extract_patents(official_ip)
        source_name = 'data-original-title-ko'
        self.assertIn(source_name, official_ip)
        with self.assertRaisesRegex(check.ExtractionError, 'Korean original title'):
            check.extract_patents(official_ip.replace(source_name, 'data-lost-original', 1))
        # Compare a bilingual rendering of these same rows: the original and
        # the English translation are independent and must both survive the switch.
        from html import escape
        import re
        def title(m):
            return (m[1] + '><span class="lang-ko">' + m[2] + '</span>' + m[3] + '</td>')
        bilingual_ip = re.sub(r'(<td[^>]*?class="title") data-original-title-ko="([^"]+)">(.+?)</td>',
                              title, official_ip.replace('<html lang="en">','<html lang="ko">'))
        bilingual_ip = re.sub(r'<span class="lang-en" data-source-ko="([^"]+)">',r'<span class="lang-ko">\1</span><span class="lang-en">',bilingual_ip)
        def records(rows):
            return dict(patents=rows, linked_patents=[], publications=[], center={'ko':'k','en':'e'})
        self.assertEqual(check.compare(records(left), records(check.extract_patents(bilingual_ip))), [])
        visible = escape(left[0]['title_en'])
        i = bilingual_ip.index('<tbody')
        updated = bilingual_ip[:i] + bilingual_ip[i:].replace(visible, 'Incorrect English display', 1)
        mismatch = check.compare(records(left), records(check.extract_patents(updated)))
        self.assertEqual([diff['field'] for diff in mismatch], ['patents[1].title_en'])

    def test_missing_center_provenance_is_not_a_match(self):
        source = (ROOT / 'people.html').read_text(encoding='utf-8')
        with self.assertRaisesRegex(check.ExtractionError, 'Korean center'):
            check.extract_center(source.replace('data-original-center-ko', 'data-lost-center', 1))


if __name__ == '__main__':
    unittest.main()
