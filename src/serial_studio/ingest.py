"""Gutendex fetch, Gutenberg cleanup and scene chunking."""

from __future__ import annotations

import json
import re

from serial_studio.gateway import Gateway
from serial_studio.schemas import Scene, StartRun, Story

GUTENDEX = "https://gutendex.com/books"
START = re.compile(r"^\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M)
END = re.compile(r"^\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M)
# ponytail: roman-numeral ALL-CAPS headings (Holmes anthologies); #3 generalises boundary detection.
HEADING = re.compile(r"^[IVXLC]+\.\s+[^a-z\n]+$", re.M)
FOOTNOTE_BLOCK = re.compile(r"\[Footnote[^\]]*\]", re.I)
FOOTNOTE_MARK = re.compile(r"\[\d+\]")


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def ingest(gateway: Gateway, start: StartRun) -> Story:
    meta = json.loads(gateway.fetch(f"{GUTENDEX}/{start.book_id}/"))
    url = next(u for fmt, u in meta["formats"].items() if fmt.startswith("text/plain") and not u.endswith(".zip"))
    body = strip_licence(gateway.fetch(url))
    authors = ", ".join(a["name"] for a in meta.get("authors", []))
    return Story(
        id=slug(start.title),
        title=start.title,
        author=authors,
        book_id=start.book_id,
        source_url=url,
        text=clean(extract_story(body, start.title)),
    )


def strip_licence(raw: str) -> str:
    raw = raw.replace("\r\n", "\n")
    start, end = START.search(raw), END.search(raw)
    if not start or not end:
        raise ValueError("Gutenberg START/END markers not found; refusing to guess where the licence is")
    return raw[start.end() : end.start()]


def extract_story(body: str, title: str) -> str:
    """The story under the heading that names it, up to the next heading.

    A book with no matching heading is taken whole (a standalone story).
    """
    core = re.sub(r"^the\s+", "", title.strip(), flags=re.I).upper()
    headings = list(HEADING.finditer(body))
    for i, h in enumerate(headings):
        if core in h.group().upper():
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            return body[h.end() : end]
    if not headings:
        return body
    raise ValueError(f"no heading matching {title!r}; headings: {[h.group() for h in headings]}")


def clean(text: str) -> str:
    """Paragraphs joined onto one line each, separated by one blank line."""
    text = FOOTNOTE_MARK.sub("", FOOTNOTE_BLOCK.sub("", text))
    paragraphs = (re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text))
    return "\n\n".join(re.sub(r"_([^_]+)_", r"\1", p) for p in paragraphs if p)


def scenes(text: str, target_words: int = 1200) -> list[Scene]:
    """Pack whole paragraphs into chunks of about target_words.

    ponytail: fixed-size paragraph packing, not true scene detection; upgrade if
    extraction misses details that straddle a chunk boundary.
    """
    bounds: list[tuple[int, int]] = []
    start, words = 0, 0
    for p in re.finditer(r"[^\n]+", text):
        words += len(p.group().split())
        if words >= target_words:
            bounds.append((start, p.end()))
            start, words = p.end() + 2, 0
    if start < len(text):
        if bounds and words < target_words // 3:
            bounds[-1] = (bounds[-1][0], len(text))  # fold a short tail into the last chunk
        else:
            bounds.append((start, len(text)))
    return [Scene(index=i, start=s, end=e, text=text[s:e]) for i, (s, e) in enumerate(bounds)]
