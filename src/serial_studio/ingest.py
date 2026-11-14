"""Gutendex fetch, Gutenberg cleanup, story boundaries, near-duplicates and scene chunking."""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any
from urllib.parse import quote_plus

from serial_studio.gateway import Gateway
from serial_studio.schemas import Copy, Scene, StartRun, Story

GUTENDEX = "https://gutendex.com/books"
START = re.compile(r"^\*\*\* ?START OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M)
END = re.compile(r"^\*\*\* ?END OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M)
# A heading stands alone between blank lines at column 0, so indented contents lists never match.
STANDALONE = re.compile(r"(?<=\n\n)\S[^\n]{0,79}(?=\n\n)")
LABEL = re.compile(r"^([A-Z][a-z]+) [IVXLC]+\.?$")  # "Adventure VIII", "Chapter IV"
NUMBERED = re.compile(r"^[IVXLC]+\.\s")  # "VIII. THE ADVENTURE OF ...", "I. Silver Blaze"
FOOTNOTE_BLOCK = re.compile(r"\[(?:Footnote|Illustration)[^\]]*\]", re.I)
FOOTNOTE_MARK = re.compile(r"\[\d+\]")
# Artefacts that damage the text. _italics_ is not one: it is faithful formatting that clean() removes.
NOISE = re.compile(r"\[(?:Illustration|Footnote|Transcriber|Pg)|[*{}|#<>\ufffd]")
SAME_STORY = 0.8  # MinHash Jaccard on 5-word shingles at or above this = the same story
PERMUTATIONS = 128
_PRIME = (1 << 61) - 1
_rng = random.Random(1661)  # fixed seed: signatures are comparable across runs
_PERMS = [(_rng.randrange(1, _PRIME), _rng.randrange(_PRIME)) for _ in range(PERMUTATIONS)]


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def ingest(gateway: Gateway, start: StartRun) -> Story:
    """The story from the requested book, swapped for the cleanest copy found anywhere on Gutenberg."""
    meta = _book(gateway, start.book_id)
    seed = _story_in(gateway, meta, start.title)
    if seed is None:
        raise ValueError(f"book {start.book_id} has no plain-text copy of {start.title!r}")
    seed_sig = minhash(clean(seed[1]))
    copies: list[tuple[Copy, str]] = []
    for m in _candidates(gateway, meta, start.title):
        found = seed if m["id"] == meta["id"] else _story_in(gateway, m, start.title)
        if found is None:
            continue
        url, raw = found
        similarity = jaccard(seed_sig, minhash(clean(raw)))
        if similarity >= SAME_STORY:
            copies.append((Copy(book_id=m["id"], source_url=url, similarity=similarity, noise=noise(raw)), raw))
    copies.sort(key=lambda c: (c[0].noise, c[0].book_id))  # deterministic: cleanest, then oldest id
    canonical, raw = copies[0]
    return Story(
        id=slug(start.title),
        title=start.title,
        author=", ".join(a["name"] for a in meta.get("authors", [])),
        book_id=canonical.book_id,
        source_url=canonical.source_url,
        text=clean(raw),
        lineage=[c for c, _ in copies],
    )


def _book(gateway: Gateway, book_id: int) -> dict[str, Any]:
    meta: dict[str, Any] = json.loads(gateway.fetch(f"{GUTENDEX}/{book_id}/"))
    return meta


def _candidates(gateway: Gateway, meta: dict[str, Any], title: str) -> list[dict[str, Any]]:
    """Books that may hold the story: other editions of this book and books named after the story.

    ponytail: first page of two title searches; a story reprinted in a differently named anthology is
    missed. Upgrade path: page through the author's whole Gutendex list.
    """
    authors = {a["name"] for a in meta.get("authors", [])}
    found = {meta["id"]: meta}
    for query in (_search_terms(meta["title"]), _search_terms(title)):
        results = json.loads(gateway.fetch(f"{GUTENDEX}/?search={quote_plus(query)}"))["results"]
        for b in results:
            if b["languages"] == meta["languages"] and authors & {a["name"] for a in b.get("authors", [])}:
                found.setdefault(b["id"], b)
    return [found[k] for k in sorted(found)]


def _search_terms(title: str) -> str:
    """Gutendex matches every word, so drop articles and subtitles that other editions word differently."""
    main = re.split(r"[:;$]", title)[0]
    return " ".join(w for w in re.findall(r"[\w'-]+", main) if w.lower() not in {"the", "a", "an", "of", "and"})


def _text_url(meta: dict[str, Any]) -> str | None:
    """Plain-text edition; audiobook releases list only a readme under text/plain."""
    urls = [u for f, u in meta["formats"].items() if f.startswith("text/plain") and not u.endswith(".zip")]
    return next((u for u in urls if "readme" not in u.lower()), None)


def _story_in(gateway: Gateway, meta: dict[str, Any], title: str) -> tuple[str, str] | None:
    """(source url, raw story text) if the book has a plain-text copy of the story."""
    url = _text_url(meta)
    if url is None:
        return None
    try:
        return url, extract_story(strip_licence(gateway.fetch(url)), title)
    except ValueError:
        return None


def strip_licence(raw: str) -> str:
    raw = re.sub(r"[ \t]+\n", "\n", raw.replace("\r\n", "\n"))
    start, end = START.search(raw), END.search(raw)
    if not start or not end:
        raise ValueError("Gutenberg START/END markers not found; refusing to guess where the licence is")
    return raw[start.end() : end.start()]


def _kind(line: str) -> str | None:
    if m := LABEL.match(line):
        return m.group(1)
    if NUMBERED.match(line):
        return "numbered"
    if re.search("[A-Z]", line) and line == line.upper():
        return "caps"
    return None


def _words(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.upper()))


def extract_story(body: str, title: str) -> str:
    """The story under the heading that names it, up to the next heading of the same kind.

    A label heading just above the title ("Adventure VIII" over "THE ADVENTURE OF ...") sets the kind,
    so the story ends at "Adventure IX". A book with no headings is taken whole (a standalone story).

    ponytail: the last story in a book runs to the licence; trailing matter ("THE END") stays in.
    """
    core = _words(re.sub(r"^the\s+", "", title.strip(), flags=re.I))
    heads = [(m.start(), m.end(), k, m.group()) for m in STANDALONE.finditer(body) if (k := _kind(m.group()))]
    for i, (s, e, kind, text) in enumerate(heads):
        if core not in _words(text):
            continue
        prev = heads[i - 1] if i else None
        if prev and prev[2] != "caps" and not body[prev[1] : s].strip():
            kind = prev[2]
        end = next((h[0] for h in heads[i + 1 :] if h[2] == kind), len(body))
        return body[e:end]
    if not heads:
        return body
    raise ValueError(f"no heading matching {title!r}; headings: {[h[3] for h in heads]}")


def noise(raw: str) -> float:
    return round(1000 * len(NOISE.findall(raw)) / max(1, len(raw.split())), 2)


def minhash(text: str) -> list[int]:
    """MinHash signature over 5-word shingles (lowercased words)."""
    words = re.findall(r"\w+", text.lower())
    hashes = {
        int.from_bytes(hashlib.blake2b(" ".join(words[i : i + 5]).encode(), digest_size=8).digest(), "big")
        for i in range(max(1, len(words) - 4))
    }
    return [min((a * h + b) % _PRIME for h in hashes) for a, b in _PERMS]


def jaccard(a: list[int], b: list[int]) -> float:
    """Estimated Jaccard similarity of the two shingle sets."""
    return round(sum(x == y for x, y in zip(a, b, strict=True)) / len(a), 3)


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
