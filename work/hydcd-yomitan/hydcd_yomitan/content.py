from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any, Iterable
from urllib.parse import quote as urlquote

from lxml import etree, html

from .models import ConversionStats, ParsedEntry
from .readings import extract_pronunciation, normalize_pinyin
from .resources import ResourceCatalog


FORBIDDEN = {"script", "style", "link", "iframe", "object", "embed", "form", "input", "button", "audio", "video"}
BLOCK_TAGS = {
    "article", "section", "div", "p", "hdcs", "hdc", "item", "items", "mean", "submeans",
    "submean", "example", "note", "notes", "examplenote", "see", "sourcedetail", "standard",
    "consultword", "chapter", "vc", "mn", "math", "mfrac", "mrow", "mroot", "msqrt",
    "mmultiscripts", "mprescripts",
}
INLINE_KINDS = {
    "u": "proper", "book": "book", "bookname": "book", "fullbookname": "book",
    "sourcetitle": "book", "source": "source-label", "type": "part-of-speech", "ref": "reference", "duyin": "reading-note",
    "tradition": "alternate", "simp": "alternate", "simplified": "alternate",
    "em": "emphasis", "b": "emphasis", "mi": "math-identifier", "mo": "math-operator",
    "strong": "emphasis", "i": "emphasis",
}
KNOWN = BLOCK_TAGS | INLINE_KINDS.keys() | {
    "a", "br", "img", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "ol", "ul", "li",
    "details", "summary", "span", "sup", "sub", "quote", "xh", "xh2", "defnum", "pron", "yinyun",
    "hm", "hw", "examples", "label", "nav1", "sensenum",
}
REDIRECT_RE = re.compile(r"^\s*@@@LINK=(.*?)\s*$", re.S)
FORM_TAGS = {"simp", "simplified", "tradition"}


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\x00", "")).strip()


def redirect_target(raw: bytes | str) -> str | None:
    text = raw.decode("utf-8", "strict") if isinstance(raw, bytes) else raw
    match = REDIRECT_RE.match(text.replace("\x00", ""))
    return normalize_text(match.group(1)) if match else None


def is_navigation_record(headword: str, raw: str) -> bool:
    lowered = raw.casefold()
    return (
        (headword.startswith("x") and "<hdcs" not in lowered and "<ul" in lowered)
        or ("class=\"entry-id\"" in lowered and "<hdcs" not in lowered and "<ul" in lowered)
    )


def is_navigation_redirect(headword: str, target: str) -> bool:
    return headword.startswith("x") and target.startswith("x")


def _append(target: list[Any], value: Any) -> None:
    if value is None or value == "":
        return
    if isinstance(value, list):
        for item in value:
            _append(target, item)
    elif isinstance(value, str) and target and isinstance(target[-1], str):
        target[-1] += value
    else:
        target.append(value)


def _content(el: etree._Element, converter: "StructuredConverter") -> list[Any]:
    result: list[Any] = []
    if el.text:
        _append(result, unicodedata.normalize("NFC", el.text))
    for child in el:
        _append(result, converter.convert(child))
        if child.tail:
            _append(result, unicodedata.normalize("NFC", child.tail))
    return result


def _strip_literal_corner_brackets(content: list[Any]) -> bool:
    """Remove a literal 「…」 pair wrapping quote content.

    The source stylesheet draws corner brackets around every ``<quote>`` except in
    ``<hdcs class="fw">`` records, which carry the brackets as literal text. The
    packaged stylesheet applies brackets to every quote, so literal ones are
    dropped here to avoid rendering them twice.
    """
    if not content or not isinstance(content[0], str) or not isinstance(content[-1], str):
        return False
    first, last = content[0], content[-1]
    if len(content) == 1:
        if not (len(first) >= 2 and first.startswith("「") and first.endswith("」")):
            return False
        content[0] = first[1:-1]
    else:
        if not (first.startswith("「") and last.endswith("」")):
            return False
        content[0] = first[1:]
        content[-1] = last[:-1]
    if content and content[-1] == "":
        content.pop()
    if content and content[0] == "":
        content.pop(0)
    return True


def _container(tag: str, content: Any, kind: str | None = None, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"tag": tag}
    if content not in (None, [], ""):
        node["content"] = content
    if kind:
        node["data"] = {"content": kind}
    node.update(extra)
    return node


def _deduplicate_terms(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = normalize_text(value)
        if value and value not in result:
            result.append(value)
    return result


def _form_row(
    expression: str,
    simplified_terms: Iterable[str] = (),
    traditional_terms: Iterable[str] = (),
) -> dict[str, Any]:
    supplied_traditional = _deduplicate_terms(traditional_terms)
    traditional = supplied_traditional or _deduplicate_terms([expression])
    simplified = _deduplicate_terms(
        ([expression] if supplied_traditional else []) + list(simplified_terms)
    )
    simplified = [value for value in simplified if value not in traditional]
    badges = [
        _container("span", value, "traditional-term")
        for value in traditional
    ]
    badges.extend(
        _container("span", value, "simplified-term")
        for value in simplified
    )
    return _container(
        "span",
        [_container("span", badges, "terms-parent")],
        "first-row-parent",
    )


class StructuredConverter:
    def __init__(self, resources: ResourceCatalog | None, stats: ConversionStats):
        self.resources = resources
        self.stats = stats

    def convert(self, el: etree._Element) -> Any:
        tag = str(el.tag).casefold() if isinstance(el.tag, str) else ""
        if not tag:
            return ""
        content = _content(el, self)
        if tag not in KNOWN:
            self.stats.unknown_tags[tag] += 1
            return content
        if tag in FORBIDDEN:
            return ""
        if tag == "br":
            return {"tag": "br"}
        if tag == "img":
            src = el.get("src", "")
            if not src or "://" in src and not src.startswith("bres://"):
                self.stats.counters["discarded_remote_images"] += 1
                return el.get("alt", "")
            if self.resources is None:
                raise FileNotFoundError(f"No resource catalog available for image {src}")
            path = self.resources.resolve(src)
            return {
                "tag": "img", "path": path, "alt": el.get("alt", ""), "title": el.get("title", ""),
                "collapsible": True, "collapsed": False, "background": True,
                "data": {"content": "entry-image"},
            }
        if tag == "a":
            href = el.get("href", "")
            if href.startswith("entry://"):
                target = normalize_text(href.removeprefix("entry://"))
                return {"tag": "a", "href": f"?query={urlquote(target)}", "content": content}
            return content
        if tag == "quote":
            if _strip_literal_corner_brackets(content):
                self.stats.counters["quote_literal_brackets_stripped"] += 1
            return _container("span", content, "quote")
        if tag in {"xh", "defnum", "sensenum"}:
            return _container("span", content, "sense-number")
        if tag in {"sup", "sub"}:
            return _container(
                "span", content, tag,
                style={"verticalAlign": "super" if tag == "sup" else "sub", "fontSize": ".78em"},
            )
        if tag in INLINE_KINDS:
            style = None
            if tag in {"em", "b", "strong"}:
                style = {"fontWeight": "bold"}
            elif tag == "i":
                style = {"fontStyle": "italic"}
            return _container("span", content, INLINE_KINDS[tag], **({"style": style} if style else {}))
        if tag == "pron":
            return _container("span", content, "pronunciation")
        if tag == "yinyun":
            return _container("div", content, "phonology")
        if tag == "examples":
            return {
                "tag": "details", "open": False, "data": {"content": "examples"},
                "content": [
                    {"tag": "summary", "content": "例证"},
                    {"tag": "div", "content": content},
                ],
            }
        if tag == "example":
            return _container("div", content, "example")
        if tag in {"note", "notes", "examplenote"}:
            return _container("div", content, "note")
        if tag == "submean":
            return _container("div", content, "subsense")
        if tag == "mean":
            return _container("div", content, "sense")
        if tag == "item":
            return _container("div", content, "item")
        if tag in {"table", "thead", "tbody", "tfoot", "tr"}:
            return _container(tag, content)
        if tag in {"td", "th"}:
            extra: dict[str, Any] = {}
            if (value := el.get("colspan")) and value.isdigit():
                extra["colSpan"] = int(value)
            if (value := el.get("rowspan")) and value.isdigit():
                extra["rowSpan"] = int(value)
            return _container(tag, content, **extra)
        if tag in {"ol", "ul", "li", "details", "summary"}:
            return _container(tag, content)
        if tag == "label":
            return _container("span", content, "label")
        if tag == "nav1":
            return _container("span", content, "navigation")
        if tag in BLOCK_TAGS:
            kind = tag.replace("_", "-")
            return _container("div", content, kind)
        return content


def _remove_forbidden(root: etree._Element) -> None:
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.casefold()
        for name in list(el.attrib):
            if name.casefold().startswith("on") or name.casefold() in {"style", "class", "id", "srcset"}:
                del el.attrib[name]
        if tag in FORBIDDEN:
            el.drop_tree()


def _text_without_sup(el: etree._Element | None) -> str:
    if el is None:
        return ""
    clone = deepcopy(el)
    for sup in clone.xpath(".//sup"):
        sup.drop_tree()
    return normalize_text("".join(clone.itertext()))


def _pua_scan(values: Iterable[str], headword: str, stats: ConversionStats) -> None:
    found = False
    for value in values:
        if any(unicodedata.category(char) == "Co" for char in value):
            found = True
            break
    if found:
        stats.counters["entries_with_unresolved_pua"] += 1
        stats.sample(stats.unresolved_pua_samples, headword)


def parse_record(
    headword: str,
    raw: str,
    resources: ResourceCatalog | None,
    stats: ConversionStats,
) -> list[ParsedEntry]:
    raw = raw.replace("\x00", "")
    try:
        root = html.fragment_fromstring(raw, create_parent="div")
    except (etree.ParserError, ValueError) as exc:
        stats.warning(f"Malformed HTML for {headword}: {exc}")
        text = normalize_text(re.sub(r"<[^>]+>", "", raw))
        return [ParsedEntry(headword, "", [{"type": "text", "text": text}])]
    _remove_forbidden(root)
    converter = StructuredConverter(resources, stats)
    hdc_nodes = root.xpath(".//hdc")
    parsed: list[ParsedEntry] = []
    if hdc_nodes:
        for hdc in hdc_nodes:
            hm = hdc.find("hm")
            hw = hm.find(".//div[@class='hw']") if hm is not None else None
            if hw is None and hm is not None:
                hw = hm.find(".//hw")
            expression = _text_without_sup(hw) or headword
            pron = hm.find(".//pron") if hm is not None else None
            pronunciation = extract_pronunciation(pron)
            if pron is not None:
                stats.record_reading(headword, pronunciation.original, pronunciation.readings, pronunciation.reasons)
            alternates: list[str] = []
            simplified_terms: list[str] = []
            traditional_terms: list[str] = []
            if hm is not None:
                for selector in ("simp", "simplified", "tradition"):
                    for node in hm.findall(f".//{selector}"):
                        value = normalize_text("".join(node.itertext()))
                        if value:
                            target = traditional_terms if selector == "tradition" else simplified_terms
                            if value not in target:
                                target.append(value)
                        if value and value != expression and value not in alternates:
                            alternates.append(value)
            header_content: list[Any] = []
            if hm is not None:
                for child in hm:
                    tag = str(child.tag).casefold() if isinstance(child.tag, str) else ""
                    if tag in {"div", "hw", "pron"} | FORM_TAGS:
                        continue
                    _append(header_content, converter.convert(child))
            body_content: list[Any] = [
                _form_row(expression, simplified_terms, traditional_terms),
            ]
            if header_content:
                body_content.append(_container("div", header_content, "header"))
            for child in hdc:
                if child is hm:
                    continue
                _append(body_content, converter.convert(child))
            if len(body_content) == 1:
                body_content.append("（无可显示释义）")
                stats.counters["empty_glossaries"] += 1
            reading_metadata: list[Any] = []
            if pronunciation.retain_source and pron is not None:
                reading_metadata = ["原文读音：", converter.convert(pron)]
                if pronunciation.unresolved_codepoints:
                    reading_metadata.append("（未解析字符：" + ", ".join(pronunciation.unresolved_codepoints) + "）")
            elif pronunciation.notes:
                reading_metadata = ["读音附注："]
                for index, note in enumerate(pronunciation.notes):
                    if index:
                        reading_metadata.append("；")
                    _append(reading_metadata, converter.convert(note))
            if reading_metadata:
                metadata = _container("div", reading_metadata, "reading-metadata")
                if header_content:
                    header_content.append(metadata)
                else:
                    body_content.insert(1, _container("div", [metadata], "header"))
            glossary = [{
                "type": "structured-content",
                "content": _container("span", body_content, "hydcd-entry", lang="zh-Hans"),
            }]
            if pronunciation.readings == [""]:
                stats.counters["missing_readings"] += 1
                stats.sample(stats.missing_reading_samples, expression)
            _pua_scan([expression, "".join(hdc.itertext())], expression, stats)
            for reading in pronunciation.readings:
                parsed.append(ParsedEntry(expression, reading, glossary, alternates))
    else:
        content: list[Any] = []
        for child in root:
            _append(content, converter.convert(child))
        if not content:
            text = normalize_text("".join(root.itertext()))
            content = [text or "（无可显示释义）"]
        body_content = [
            _form_row(headword),
            _container("div", content, "generic-content"),
        ]
        glossary = [{
            "type": "structured-content",
            "content": _container("span", body_content, "hydcd-entry", lang="zh-Hans"),
        }]
        parsed.append(ParsedEntry(headword, "", glossary))
        stats.counters["generic_records"] += 1
        _pua_scan([headword, "".join(root.itertext())], headword, stats)
    return parsed
