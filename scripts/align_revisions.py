#!/usr/bin/env python3
"""Find text differences to review. Candidate blocks require contextual verification."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PARAGRAPH = W + "p"
HIDDEN_REVISIONS = {W + "del", W + "moveFrom"}
EXCLUDED_CONTENT = {W + name for name in ("drawing", "pict", "object", "txbxContent", "altChunk")}
REVISION_TAGS = HIDDEN_REVISIONS | {
    W + name for name in ("ins", "moveTo", "pPrChange", "rPrChange", "tblPrChange", "sectPrChange")
}
MARKDOWN_HEADING = re.compile(r"^[ ]{0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")


@dataclass(frozen=True)
class Paragraph:
    locator: str
    text: str


def text_in_paragraph(element: ET.Element) -> str:
    if element.tag in HIDDEN_REVISIONS or element.tag in EXCLUDED_CONTENT:
        return ""
    if element.tag == W + "t":
        return element.text or ""
    if element.tag in {W + "br", W + "cr"}:
        return "\n"
    if element.tag == W + "tab":
        return "\t"
    if element.tag == W + "noBreakHyphen":
        return "\u2011"
    return "".join(text_in_paragraph(child) for child in element)


def docx_paragraphs(raw: bytes) -> tuple[list[Paragraph], dict, list[str]]:
    with ZipFile(BytesIO(raw)) as archive:
        parts = set(archive.namelist())
        main = ET.fromstring(archive.read("word/document.xml"))
        classic_comments = (
            len(list(ET.fromstring(archive.read("word/comments.xml")).iter(W + "comment")))
            if "word/comments.xml" in parts else 0
        )
    body = main.find(W + "body")
    if body is None:
        raise ValueError("DOCX has no supported main document body")
    physical_indices = {p: i for i, p in enumerate(body.iter(PARAGRAPH), 1)}
    paragraphs = []

    def include(element: ET.Element) -> None:
        if element.tag in HIDDEN_REVISIONS or element.tag in EXCLUDED_CONTENT:
            return
        if element.tag == PARAGRAPH:
            text = text_in_paragraph(element).strip()
            if text:
                paragraphs.append(Paragraph(f"p{physical_indices[element]}", text))
            return
        for child in element:
            include(child)

    include(body)
    structural = {
        "physical_paragraphs": len(physical_indices),
        "tracked_revision_elements": sum(e.tag in REVISION_TAGS for e in body.iter()),
        "classic_comments": classic_comments,
        "tables": len(list(body.iter(W + "tbl"))),
        "media_parts": sum(part.startswith("word/media/") and not part.endswith("/") for part in parts),
        "footnotes_part": "word/footnotes.xml" in parts,
        "endnotes_part": "word/endnotes.xml" in parts,
    }
    warnings = []
    if structural["tracked_revision_elements"]:
        warnings.append("Inserted text included and deleted or moved-from text skipped. Paragraph-mark, table, and formatting revisions require review in Word.")
    if classic_comments or any(part.startswith("word/comments") for part in parts):
        warnings.append("Comment text is outside the compared body. Consult the source comments separately.")
    if structural["tables"]:
        warnings.append("Table cell text is read in XML order. Merges, row and column changes, and visual layout require separate review.")
    if structural["media_parts"] or any(e.tag in EXCLUDED_CONTENT for e in body.iter()):
        warnings.append("Images, embedded objects, text boxes, or imported content are outside the compared body.")
    if structural["footnotes_part"] or structural["endnotes_part"]:
        warnings.append("Footnote and endnote text is outside the compared body.")
    if any(re.fullmatch(r"word/(?:header|footer)\d*\.xml", part) for part in parts):
        warnings.append("Headers and footers are outside the compared body.")
    return paragraphs, structural, warnings


def read_document(path: Path, start: str | None) -> tuple[list[Paragraph], dict]:
    suffix = path.suffix.lower()
    if suffix not in {".docx", ".txt", ".md", ".markdown"}:
        raise ValueError(f"Unsupported document type: {suffix or '(no extension)'}")
    raw = path.read_bytes()
    if suffix == ".docx":
        paragraphs, structural, warnings = docx_paragraphs(raw)
        locator_system = "pN = 1-based paragraph in DOCX main body XML, including empty or skipped nodes in numbering"
    else:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Plain text contains NUL characters")
        paragraphs = [
            Paragraph(f"L{i}", line.strip()) for i, line in enumerate(text.splitlines(), 1)
            if line.strip()
        ]
        structural = {}
        warnings = ["Plain-text comparison uses non-empty lines. Soft line wrapping can affect alignment."]
        locator_system = "LN = 1-based file line"
    if not paragraphs:
        raise ValueError("No readable text in supported document body")
    excluded_count = 0
    if start is not None:
        title = start.strip()
        matches = []
        for index, paragraph in enumerate(paragraphs):
            heading = MARKDOWN_HEADING.fullmatch(paragraph.text) if suffix in {".md", ".markdown"} else None
            if paragraph.text == title or (heading and heading[1].strip() == title):
                matches.append(index)
        if len(matches) != 1:
            raise ValueError(f"Start title must match exactly once, but matched {len(matches)} paragraphs or lines")
        excluded_count = matches[0]
        paragraphs = paragraphs[excluded_count:]
    return paragraphs, {
        "file_sha256": sha256(raw).hexdigest(),
        "format": suffix[1:],
        "compared_paragraphs": len(paragraphs),
        "preceding_text_paragraphs_excluded": excluded_count,
        "locator_system": locator_system,
        "structural": structural,
        "warnings": warnings,
    }


def span(paragraphs: list[Paragraph]) -> dict | None:
    if not paragraphs:
        return None
    return {"start": paragraphs[0].locator, "end": paragraphs[-1].locator, "count": len(paragraphs)}


def contextual_text(paragraphs: list[Paragraph]) -> list[dict]:
    return [{"locator": p.locator, "text": p.text} for p in paragraphs]


def block_alignment(before: list[Paragraph], after: list[Paragraph], include_text: bool) -> dict:
    before_values = [paragraph.text for paragraph in before]
    after_values = [paragraph.text for paragraph in after]
    before_counts, after_counts = Counter(before_values), Counter(after_values)
    exact_anchors, candidate_blocks = [], []
    unmatched_before, unmatched_after = {}, {}
    matcher = SequenceMatcher(None, before_values, after_values, autojunk=False)
    for tag, i, j, k, m in matcher.get_opcodes():
        earlier, later = before[i:j], after[k:m]
        if tag == "equal":
            repeated = any(before_counts[p.text] > 1 or after_counts[p.text] > 1 for p in earlier)
            exact_anchors.append({"before": span(earlier), "after": span(later), "contains_repeated_text": repeated})
            continue
        block = {
            "before": span(earlier),
            "after": span(later),
            "before_between": [before[i - 1].locator if i > 0 else None, before[j].locator if j < len(before) else None],
            "after_between": [after[k - 1].locator if k > 0 else None, after[m].locator if m < len(after) else None],
            "text_operation": tag,
            "alignment": "candidate",
            "review": "Check moved, merged, split, or repeated material before interpreting this block.",
        }
        if include_text:
            block["before_text"] = contextual_text(earlier)
            block["after_text"] = contextual_text(later)
        candidate_blocks.append(block)
        unmatched_before.update((p.text, p.locator) for p in earlier if before_counts[p.text] == 1)
        unmatched_after.update((p.text, p.locator) for p in later if after_counts[p.text] == 1)
    moves = [
        {"before": old, "after": unmatched_after[text], "alignment": "candidate"}
        for text, old in unmatched_before.items() if text in unmatched_after
    ]
    return {"exact_anchors": exact_anchors, "candidate_blocks": candidate_blocks, "possible_exact_moves": moves}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--before-start", help="Start comparison at this exact paragraph or line")
    parser.add_argument("--after-start", help="Start comparison at this exact paragraph or line")
    parser.add_argument("--include-text", action="store_true", help="Include source text in changed blocks for local review")
    args = parser.parse_args()
    try:
        before, before_meta = read_document(args.before, args.before_start)
        after, after_meta = read_document(args.after, args.after_start)
    except (OSError, ValueError, BadZipFile, ET.ParseError, KeyError) as error:
        parser.error(str(error))
    output = {
        "schema_version": 1,
        "source_text_included": args.include_text,
        "before": before_meta,
        "after": after_meta,
        **block_alignment(before, after, args.include_text),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
