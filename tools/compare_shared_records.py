#!/usr/bin/env python3
"""Read-only comparison of the two P2E sites' shared public records (stdlib only)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from http.client import HTTPException
from html.parser import HTMLParser
from itertools import zip_longest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORIES = {
    "official": "p2e-research-group/p2e-research-group.github.io",
    "reference": "Dochi37-cpu/Dochi37-cpu.github.io",
}
FILES = ("ip.html", "publications.html", "people.html")
EXIT_CODES = {"MATCH": 0, "EXTRACTED": 0, "MISMATCH": 1,
              "EXTRACTION_ERROR": 2, "DEFERRED": 3}
VOID = set("area base br col embed hr img input link meta param source track wbr".split())
DASHES = str.maketrans({c: "-" for c in "‐‑‒–—−"})


class ExtractionError(ValueError):
    """A required source structure or field cannot be interpreted safely."""


class RemoteUnavailable(OSError):
    """A bounded remote request failed; comparison must be deferred."""


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(DASHES).split())


def key(text: str) -> str:
    # Ignore spacing/line wrapping, not words, punctuation, or chemical case.
    return re.sub(r"\s+", "", normalize(text))


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    children: list = field(default_factory=list)

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def elements(self):
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.elements()

    def text(self, breaks="\n") -> str:
        if self.tag == "br":
            return breaks
        return "".join(c.text(breaks) if isinstance(c, Element) else c for c in self.children)


class Document(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Element("document", {})
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Element(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def one(nodes, context: str) -> Element:
    nodes = list(nodes)
    if len(nodes) != 1:
        raise ExtractionError(f"{context}: expected one element, found {len(nodes)}")
    return nodes[0]


def by_class(node: Element, name: str):
    return [e for e in node.elements() if e.has_class(name)]


def nonempty(text: str, context: str) -> str:
    value = normalize(text)
    if not value:
        raise ExtractionError(f"{context}: empty value")
    return value


def identifier(text: str) -> str:
    value = re.sub(r"[\s-]", "", normalize(text)).upper()
    if not re.fullmatch(r"(?:[A-Z]{2})?\d+(?:[A-Z]\d?)?", value):
        raise ExtractionError(f"invalid patent identifier: {text!r}")
    # These records use Korean identifiers. An optional KR prefix is display-only;
    # other country prefixes and kind codes are retained, never guessed/deleted.
    return value[2:] if value.startswith("KR") else value


ID_PATTERN = re.compile(
    r"(?P<label>App(?:lication)?|Pub(?:lication)?|Reg(?:istration)?)\.?"
    r"(?:\s+No\.?)?\s*[:#]?\s*"
    r"(?P<value>(?:[A-Za-z]{2}\s*)?\d+(?:[\s-]+\d+)*(?:[A-Z]\d?)?)",
    re.IGNORECASE,
)
ID_KINDS = {"app": "application", "pub": "publication", "reg": "registration"}


def patent_identifiers(row: Element, cell: Element, context: str) -> dict:
    values = {kind: set() for kind in ID_KINDS.values()}
    shown = normalize(cell.text())
    matches = list(ID_PATTERN.finditer(shown))
    residue = ID_PATTERN.sub("", shown)
    if not matches or re.sub(r"[\s/;,|]", "", residue):
        raise ExtractionError(f"{context}: unrecognized identifier display {shown!r}")
    for match in matches:
        kind = ID_KINDS[match["label"][:3].lower()]
        values[kind].add(identifier(match["value"]))
    for element in [row, *row.elements()]:
        for kind in values:
            attr = f"data-{kind}-number"
            if attr in element.attrs:
                values[kind].add(identifier(element.attrs[attr]))
    for kind, numbers in values.items():
        if len(numbers) > 1:
            raise ExtractionError(f"{context}: conflicting {kind} identifiers {sorted(numbers)}")
    return {kind: next(iter(numbers), None) for kind, numbers in values.items()}


def extract_patents(source: str) -> list[dict]:
    root = Document(source).root
    table = one(by_class(root, "registry-table"), "ip.html registry table")
    tbody = one((e for e in table.elements() if e.tag == "tbody"), "ip.html registry tbody")
    rows = [e for e in tbody.children if isinstance(e, Element) and e.tag == "tr"]
    if not rows:
        raise ExtractionError("ip.html: no registry rows")
    records, numbers, identifiers = [], set(), set()
    for position, row in enumerate(rows, 1):
        context = f"ip.html row {position}"
        number = normalize(one(by_class(row, "no"), context + " number").text())
        if not number.isascii() or not number.isdigit() or int(number) < 1:
            raise ExtractionError(f"{context}: invalid row number {number!r}")
        number = int(number)
        if number in numbers:
            raise ExtractionError(f"{context}: duplicate row number {number}")
        numbers.add(number)
        title_cell = one(by_class(row, "title"), context + " title")
        # Compare the Korean original, not an original + display-translation join.
        # Legacy reference markup is plain Korean; bilingual markup is explicit.
        if by_class(title_cell, "lang-ko") or by_class(title_cell, "lang-en"):
            original = one(by_class(title_cell, "lang-ko"), context + " original title")
            translation = one(by_class(title_cell, "lang-en"), context + " translated title")
            nonempty(translation.text(), context + " translated title")
            title = nonempty(original.text(), context + " original title")
        else:
            title = nonempty(title_cell.text(), context + " title")
        cell = one(by_class(row, "pubno"), context + " identifiers")
        ids = patent_identifiers(row, cell, context)
        for kind, value in ids.items():
            if value is not None:
                if (kind, value) in identifiers:
                    raise ExtractionError(f"{context}: duplicate {kind} identifier {value}")
                identifiers.add((kind, value))
        status = one(by_class(row, "status-pill"), context + " status")
        record = {"number": number, "title": title, **ids}
        for lang in ("ko", "en"):
            value = one(by_class(status, f"lang-{lang}"), context + f" status ({lang})")
            record[f"status_{lang}"] = nonempty(value.text(), context)
        records.append(record)
    return records


def extract_publications(source: str) -> list[str]:
    root = Document(source).root
    listing = one(by_class(root, "publication-list"), "publications.html publication list")
    items = by_class(listing, "publication-item")
    if not items:
        raise ExtractionError("publications.html: no publication items")
    return [nonempty(one(by_class(item, "pub-title"), f"publication {i} title").text(),
                     f"publication {i}") for i, item in enumerate(items, 1)]


def extract_center(source: str) -> dict[str, str]:
    root = Document(source).root
    summary = one(by_class(root, "profile-facts"), "people.html PI profile summary")
    heading_tags = {"b", "strong", "h2", "h3", "h4"}

    def appointment_heading(element):
        return element.tag in heading_tags and normalize(element.text()).upper() in {
            "CURRENT APPOINTMENT", "현재 소속"}

    block = one((e for e in by_class(summary, "profile-fact")
                 if any(appointment_heading(h) for h in e.elements())),
                "people.html CURRENT APPOINTMENT block")
    result = {}
    for lang in ("ko", "en"):
        # R1 fix: labels may themselves have lang-ko/lang-en. Select direct VALUE
        # children, excluding heading nodes/wrappers, not a known center string.
        values = [e for e in block.children if isinstance(e, Element)
                  and e.has_class(f"lang-{lang}")
                  and not appointment_heading(e)
                  and not any(appointment_heading(h) for h in e.elements())]
        value = one(values, f"people.html CURRENT APPOINTMENT value ({lang})")
        # Source indentation/newlines are whitespace, not logical affiliation lines.
        lines = [normalize(line) for line in value.text("\0").split("\0") if normalize(line)]
        if len(lines) != 2:
            raise ExtractionError(f"people.html CURRENT APPOINTMENT ({lang}): "
                                  f"expected role/institution then center separated by br, got {len(lines)} lines")
        result[lang] = lines[1]
    return result


def extract_linked_patents(source: str) -> list[dict]:
    """Read visible international records, retaining the domestic parent relation."""
    root = Document(source).root
    records, applications, publications = [], set(), set()
    parent_rows = {normalize(one(by_class(row, 'no'), 'domestic parent').text()): row
                   for row in root.elements() if row.tag == 'tr' and by_class(row, 'no')}
    for item in by_class(root, 'ip-linked-record'):
        fields = {}
        for name in ('parent', 'jurisdiction', 'application', 'publication', 'aliases', 'stage', 'event-date'):
            value = item.attrs.get('data-' + name)
            if value is None or (not value and name != 'aliases'):
                raise ExtractionError(f'international record: missing {name}')
            fields[name.replace('-', '_')] = normalize(value)
        parent = parent_rows.get(fields['parent'])
        if parent is None or not any(e is item for e in parent.elements()):
            raise ExtractionError('international record detached from its domestic parent')
        application = (fields['jurisdiction'], key(fields['application']))
        if application in applications:
            raise ExtractionError('duplicate international application')
        applications.add(application)
        if fields['jurisdiction'] not in ('US','JP','CN','EP','WO'):
            raise ExtractionError('unknown international jurisdiction')
        if fields['stage'] not in ('granted','published','allowed','pct_published'):
            raise ExtractionError('unknown international stage')
        if (fields['jurisdiction'] == 'WO') != (fields['stage'] == 'pct_published'):
            raise ExtractionError('PCT publication must remain separate from national/regional grants')
        for value in [fields['publication'], *filter(None,fields['aliases'].split('|'))]:
            if value in publications or not value.startswith(fields['jurisdiction']):
                raise ExtractionError('duplicate or conflicting international publication')
            publications.add(value)
        publication = one(by_class(item,'ip-publication'),'international publication link')
        if normalize(publication.text()) != fields['publication']:
            raise ExtractionError('visible international identifier conflicts with data')
        stage = one(by_class(item,'ip-stage'),'international stage')
        expected = {'granted':('등록공보','Granted'),'published':('공개','Published'),
                    'allowed':('등록결정 안내','Allowance notice'),'pct_published':('PCT 국제공개','PCT publication')}
        for lang, value in zip(('ko','en'), expected[fields['stage']]):
            actual = normalize(one(by_class(stage,'lang-'+lang),'international bilingual stage').text())
            if actual != value:
                raise ExtractionError('international stage conflicts with visible bilingual label')
        fields['publication_url'] = publication.attrs.get('href','')
        fields['evidence_url'] = one(by_class(item,'ip-source'),'international evidence link').attrs.get('href','')
        if not all(fields[name].startswith('https://') for name in ('publication_url','evidence_url')):
            raise ExtractionError('missing public international evidence link')
        records.append(fields)
    return records


def extract(pages: dict[str, str]) -> dict:
    try:
        return {"patents": extract_patents(pages["ip.html"]),
                "linked_patents": extract_linked_patents(pages["ip.html"]),
                "publications": extract_publications(pages["publications.html"]),
                "center": extract_center(pages["people.html"])}
    except KeyError as exc:
        raise ExtractionError(f"missing input file: {exc}") from exc


def compare(official: dict, reference: dict) -> list[dict]:
    differences = []

    def add(path, left, right):
        same = key(left) == key(right) if isinstance(left, str) and isinstance(right, str) else left == right
        if isinstance(left, str) and isinstance(right, str) and (path.endswith('.status_en') or path == 'center.en'):
            same = key(left).casefold() == key(right).casefold()
        if not same:
            differences.append({"field": path, "official": left, "reference": right})

    for collection in ("patents", "linked_patents", "publications"):
        left_records, right_records = official.get(collection, []), reference.get(collection, [])
        add(f"{collection}.count", len(left_records), len(right_records))
        for i, (left, right) in enumerate(zip_longest(left_records, right_records), 1):
            path = f"{collection}[{i}]"
            if collection in ("patents", "linked_patents") and left is not None and right is not None:
                for field_name in left:
                    add(f"{path}.{field_name}", left[field_name], right[field_name])
            else:
                add(path + (".title" if collection == "publications" else ""), left, right)
    for lang in ("ko", "en"):
        add(f"center.{lang}", official["center"][lang], reference["center"][lang])
    return differences


class GitHubReader:
    """Anonymous public GETs only; no credentials, writes, or floating file URLs."""
    def __init__(self, attempts=3, timeout=15, opener=urlopen, sleep=time.sleep):
        self.attempts, self.timeout, self.opener, self.sleep = attempts, timeout, opener, sleep

    def read(self, url: str) -> str:
        reason = "unavailable"
        for attempt in range(self.attempts):
            try:
                request = Request(url, headers={"User-Agent": "P2E-shared-record-check/1.0",
                                               "Accept": "application/vnd.github+json" if "api.github.com" in url else "text/html"})
                with self.opener(request, timeout=self.timeout) as response:
                    payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ExtractionError(f"response too large: {url}")
                try:
                    return payload.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    raise ExtractionError(f"non-UTF-8 source: {url}") from exc
            except HTTPError as exc:
                reason = f"HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, HTTPException) as exc:
                reason = type(exc).__name__
            if attempt + 1 < self.attempts:
                self.sleep(min(2 ** attempt, 4))
        raise RemoteUnavailable(f"{url}: {reason} after {self.attempts} attempts")

    def resolve(self, repo: str) -> str:
        try:
            sha = json.loads(self.read(f"https://api.github.com/repos/{repo}/commits/main"))["sha"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExtractionError(f"{repo}: invalid main SHA response") from exc
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ExtractionError(f"{repo}: invalid commit SHA")
        return sha

    def page(self, repo: str, sha: str, filename: str) -> str:
        return self.read(f"https://raw.githubusercontent.com/{repo}/{sha}/{filename}")


def online(reader=None) -> dict:
    reader = reader or GitHubReader()
    result = {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
              "status": None, "comparison_performed": False, "sources": {},
              "differences": [], "errors": []}
    for side, repo in REPOSITORIES.items():
        result["sources"][side] = {"repository": repo, "ref": "main", "sha": None}
    # Resolve each ref once BEFORE reading any HTML. Retries concern the same
    # request; after a SHA succeeds it is never re-resolved during this run.
    for side, source in result["sources"].items():
        try:
            source["sha"] = reader.resolve(source["repository"])
        except (RemoteUnavailable, ExtractionError) as exc:
            kind = "DEFERRED" if isinstance(exc, RemoteUnavailable) else "EXTRACTION_ERROR"
            result["errors"].append({"source": side, "kind": kind, "message": str(exc)})
    for side, source in result["sources"].items():
        if source["sha"] is None:
            continue
        try:
            pages = {name: reader.page(source["repository"], source["sha"], name) for name in FILES}
            source["records"] = extract(pages)
            source["counts"] = {k: len(source["records"][k]) for k in ("patents", "linked_patents", "publications")}
        except (RemoteUnavailable, ExtractionError) as exc:
            kind = "DEFERRED" if isinstance(exc, RemoteUnavailable) else "EXTRACTION_ERROR"
            result["errors"].append({"source": side, "kind": kind, "message": str(exc)})
    if result["errors"]:
        kinds = {e["kind"] for e in result["errors"]}
        result["status"] = "EXTRACTION_ERROR" if "EXTRACTION_ERROR" in kinds else "DEFERRED"
    else:
        result["comparison_performed"] = True
        result["differences"] = compare(result["sources"]["official"]["records"],
                                        result["sources"]["reference"]["records"])
        result["status"] = "MISMATCH" if result["differences"] else "MATCH"
    return result


def summary(result: dict) -> str:
    titles = {"MATCH": "일치", "MISMATCH": "실제 불일치", "DEFERRED": "비교 보류 (원격 접근 불가)",
              "EXTRACTION_ERROR": "추출 오류", "EXTRACTED": "로컬 추출 성공 (온라인 비교 아님)"}
    lines = [f"# P2E shared public records: {result['status']}", "", titles[result["status"]], ""]
    for side, source in result.get("sources", {}).items():
        lines.append(f"- {side}: `{source['repository']}` main → `{source['sha'] or 'UNRESOLVED'}`")
        if "counts" in source:
            lines.append(f"  - Counts: {source['counts']}")
    for diff in result.get("differences", []):
        lines.extend(["", f"## {escape(diff['field'])}", "",
                      f"- official: {escape(json.dumps(diff['official'], ensure_ascii=False))}",
                      f"- reference: {escape(json.dumps(diff['reference'], ensure_ascii=False))}"])
    for error in result.get("errors", []):
        lines.append(f"\n- {error['kind']} ({error['source']}): {escape(error['message'])}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("extract", "online"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="JSON report path (outside the website recommended)")
    parser.add_argument("--summary", type=Path, help="Markdown Job Summary path")
    args = parser.parse_args(argv)
    if args.mode == "online":
        result = online()
    else:
        try:
            records = extract({name: (args.root / name).read_text(encoding="utf-8") for name in FILES})
            result = {"status": "EXTRACTED", "comparison_performed": False, "records": records}
        except (OSError, UnicodeError, ExtractionError) as exc:
            result = {"status": "EXTRACTION_ERROR", "comparison_performed": False,
                      "errors": [{"source": "local", "kind": "EXTRACTION_ERROR", "message": str(exc)}]}
    rendered = summary(result)
    # Prefix lines so remote content can never be interpreted as Actions commands.
    for line in rendered.splitlines():
        print(f"[shared-records] {line}")
    if args.mode == "extract" and result["status"] == "EXTRACTED":
        print("[shared-records] Extracted " + json.dumps({k: len(result['records'][k])
              for k in ('patents', 'linked_patents', 'publications')}))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as stream:
            stream.write(rendered)
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
