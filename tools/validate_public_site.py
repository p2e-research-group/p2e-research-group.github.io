#!/usr/bin/env python3
"""Validate the static, public-only P2E website."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://p2e-research-group.github.io/"
PUBLIC_PAGES = (
    "index.html",
    "research.html",
    "people.html",
    "publications.html",
    "ip.html",
    "join.html",
)
HTML_FILES = PUBLIC_PAGES + ("404.html",)
REQUIRED_ASSETS = (
    "assets/site.css",
    "assets/components.css",
    "assets/responsive.css",
    "assets/editorial-polish.css",
    "assets/site.js",
    "assets/p2e-favicon-v1.svg",
    "assets/p2e-wordmark-v1.svg",
    "assets/p2e-og-v1.png",
    "assets/han-sol-jung.jpg",
)
PROHIBITED_PATHS = ("group.html", "news.html", "contact.html", "assets/i18n")
PROHIBITED_TEXT = (
    "research ownership",
    "methods & research assets",
    "research assets preserve reusable learning",
    "bop model & interface library",
    "reusable plant-system assets",
    "models do not define plant reality",
    "source of truth",
    "source-of-truth",
    "public case-study standard",
    "manuscript directions",
    "authorship principle",
    "ip principle",
    "ownership ladder",
    "maturity gate",
    "evidence gate",
    "decision gate",
    "formal supervision of",
)
NAMED_COLLABORATORS = (
    "Kiwoong Kim",
    "Dowan Kim",
    "Seungjun Baek",
    "Yongtae Kim",
    "Kyungmin Lee",
    "Sun Choi",
    "Kyoungrok Kim",
    "Seunghyun Cheon",
    "Joongjin Han",
    "Gibaek Lee",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.assets: list[str] = []
        self.ids: set[str] = set()
        self.canonicals: list[str] = []
        self.og_urls: list[str] = []
        self.og_images: list[str] = []
        self.ko_count = 0
        self.en_count = 0
        self.nav_links: list[str] = []
        self._in_main_nav = False

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        element_id = attrs.get("id")
        if element_id:
            self.ids.add(element_id)
        classes = set((attrs.get("class") or "").split())
        self.ko_count += int("lang-ko" in classes)
        self.en_count += int("lang-en" in classes)
        if tag == "nav" and attrs.get("id") == "main-menu":
            self._in_main_nav = True
        if tag == "a" and attrs.get("href"):
            href = attrs["href"] or ""
            self.links.append(href)
            if self._in_main_nav:
                self.nav_links.append(href)
        if tag in {"img", "script"} and attrs.get("src"):
            self.assets.append(attrs["src"] or "")
        if tag == "link" and attrs.get("href"):
            href = attrs["href"] or ""
            if attrs.get("rel") == "canonical":
                self.canonicals.append(href)
            elif attrs.get("rel") in {"stylesheet", "icon"}:
                self.assets.append(href)
        if tag == "meta":
            prop = attrs.get("property")
            if prop == "og:url" and attrs.get("content"):
                self.og_urls.append(attrs["content"] or "")
            if prop == "og:image" and attrs.get("content"):
                self.og_images.append(attrs["content"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav" and self._in_main_nav:
            self._in_main_nav = False


def local_target(current: Path, value: str) -> tuple[Path, str | None] | None:
    if not value or value.startswith(("mailto:", "tel:", "javascript:")):
        return None
    split = urlsplit(value)
    if split.scheme or split.netloc:
        return None
    path = unquote(split.path)
    if not path:
        return current, split.fragment or None
    if path.startswith("/"):
        target = ROOT / path.lstrip("/")
    else:
        target = current.parent / path
    if target.is_dir():
        target /= "index.html"
    return target.resolve(), split.fragment or None


def canonical_for(page: str) -> str:
    return BASE_URL if page == "index.html" else BASE_URL + page


def main() -> int:
    errors: list[str] = []
    parsed: dict[Path, PageParser] = {}

    for rel in PUBLIC_PAGES + REQUIRED_ASSETS + ("robots.txt", "sitemap.xml"):
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")
    for rel in PROHIBITED_PATHS:
        if (ROOT / rel).exists():
            errors.append(f"prohibited path exists: {rel}")

    for rel in HTML_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing HTML file: {rel}")
            continue
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parsed[path.resolve()] = parser
        expected = canonical_for(rel)
        if parser.canonicals != [expected]:
            errors.append(f"{rel}: canonical must be {expected!r}")
        if parser.og_urls != [expected]:
            errors.append(f"{rel}: og:url must be {expected!r}")
        expected_image = BASE_URL + "assets/p2e-og-v1.png"
        if parser.og_images != [expected_image]:
            errors.append(f"{rel}: og:image must be {expected_image!r}")
        if parser.ko_count == 0 or parser.en_count == 0:
            errors.append(f"{rel}: missing explicit KO/EN content")
        expected_nav = ["index.html", "research.html", "people.html", "publications.html", "ip.html", "join.html"]
        observed_nav = [href.lstrip("/") for href in parser.nav_links]
        if observed_nav != expected_nav:
            errors.append(f"{rel}: primary navigation must contain the six public pages in order")

    for current, parser in list(parsed.items()):
        for value in parser.links + parser.assets:
            if "group.html" in value:
                errors.append(f"{current.name}: removed page linked: {value}")
            target_info = local_target(current, value)
            if target_info is None:
                continue
            target, fragment = target_info
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{current.name}: local target leaves repository: {value}")
                continue
            if not target.is_file():
                errors.append(f"{current.name}: broken local target: {value}")
                continue
            if fragment and target.suffix.lower() == ".html":
                target_parser = parsed.get(target)
                if target_parser is None:
                    target_parser = PageParser()
                    target_parser.feed(target.read_text(encoding="utf-8"))
                    parsed[target] = target_parser
                if fragment not in target_parser.ids:
                    errors.append(f"{current.name}: missing fragment target: {value}")

    searchable = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() not in {".html", ".js", ".json", ".md", ".txt", ".xml", ".yml", ".yaml"}:
            continue
        searchable.append((path, path.read_text(encoding="utf-8").lower()))
    for phrase in PROHIBITED_TEXT:
        for path, text in searchable:
            if phrase.lower() in text:
                errors.append(f"{path.relative_to(ROOT)}: prohibited public/internal phrase: {phrase}")
    for name in NAMED_COLLABORATORS:
        if name in (ROOT / "people.html").read_text(encoding="utf-8"):
            errors.append(f"people.html: named collaborator remains: {name}")

    people = (ROOT / "people.html").read_text(encoding="utf-8")
    if people.count('class="researcher-card"') != 3:
        errors.append("people.html: expected exactly three researcher cards")
    researcher_section = people.split('id="researchers"', 1)[-1].split('id="collaborators"', 1)[0]
    if re.search(r'class="tags"|class="interface-line"', researcher_section):
        errors.append("people.html: researcher tags or mapping blocks remain")

    publications = (ROOT / "publications.html").read_text(encoding="utf-8")
    if publications.count('class="publication-item"') != 13:
        errors.append("publications.html: expected 13 publication records")
    ip_page = (ROOT / "ip.html").read_text(encoding="utf-8")
    if len(re.findall(r'<tr><td class="no">', ip_page)) != 23:
        errors.append("ip.html: expected 23 public registry records")

    try:
        sitemap = ET.parse(ROOT / "sitemap.xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in sitemap.findall("s:url/s:loc", ns)]
        expected_urls = [canonical_for(page) for page in PUBLIC_PAGES]
        if urls != expected_urls:
            errors.append("sitemap.xml: URLs must exactly match the six canonical public pages")
    except (ET.ParseError, OSError) as exc:
        errors.append(f"sitemap.xml: parse failure: {exc}")

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    if "Disallow:" in robots or f"Sitemap: {BASE_URL}sitemap.xml" not in robots:
        errors.append("robots.txt: crawl policy or Sitemap URL is incorrect")

    if errors:
        print("Public-site validation failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print("Validated 7 HTML files, 6 canonical pages, public-only content, links, metadata and assets.")
    print("Verified 13 publications, 23 IP records and 3 researcher cards without internal detail blocks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
