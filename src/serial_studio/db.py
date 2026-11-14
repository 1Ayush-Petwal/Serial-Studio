"""Postgres store: model cache, cost lines, stories, bible versions, scripts, decision rows."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from serial_studio.schemas import Bible, CostLine, Decision, Script, Story

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS model_cache (
    key text PRIMARY KEY,
    kind text NOT NULL,           -- 'model' or 'http'
    request jsonb NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cost_lines (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    stage text NOT NULL,
    node text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    input_tokens int NOT NULL,
    output_tokens int NOT NULL,
    list_price_usd numeric(12, 8) NOT NULL,
    cache_hit boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS stories (
    id text PRIMARY KEY,
    story jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bibles (
    story_id text NOT NULL REFERENCES stories(id),
    version int NOT NULL,
    bible jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (story_id, version)
);
-- source labels a script for blind evaluation; it never goes inside the script a judge reads.
CREATE TABLE IF NOT EXISTS scripts (
    story_id text NOT NULL REFERENCES stories(id),
    source text NOT NULL CHECK (source IN ('pipeline', 'baseline')),
    episode int NOT NULL,
    script jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (story_id, source, episode)
);
CREATE TABLE IF NOT EXISTS decisions (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    gate int NOT NULL,
    target text NOT NULL,
    verdict text NOT NULL CHECK (verdict IN ('approve', 'reject')),
    notes text NOT NULL DEFAULT '',
    nudges jsonb NOT NULL DEFAULT '[]',
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


def connect(url: str) -> psycopg.Connection[dict[str, Any]]:
    # prepare_threshold=None: safe behind Supabase's pooler.
    return psycopg.connect(url, autocommit=True, row_factory=dict_row, prepare_threshold=None)


def setup(conn: psycopg.Connection[Any]) -> None:
    conn.execute(DDL)


# --- model cache (also the record/replay store) ---


def cache_get(conn: psycopg.Connection[Any], key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT response FROM model_cache WHERE key = %s", (key,)).fetchone()
    return row["response"] if row else None


def cache_put(conn: psycopg.Connection[Any], key: str, kind: str, request: Any, response: Any) -> None:
    conn.execute(
        "INSERT INTO model_cache (key, kind, request, response) VALUES (%s, %s, %s, %s) ON CONFLICT (key) DO NOTHING",
        (key, kind, Jsonb(request), Jsonb(response)),
    )


def cache_rows(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    return conn.execute("SELECT key, kind, request, response FROM model_cache ORDER BY created_at").fetchall()


# --- cost lines ---


def add_cost_line(conn: psycopg.Connection[Any], line: CostLine) -> None:
    d = line.model_dump()
    conn.execute(
        f"INSERT INTO cost_lines ({', '.join(d)}) VALUES ({', '.join(['%s'] * len(d))})",
        tuple(d.values()),
    )


def cost_lines(conn: psycopg.Connection[Any], run_id: str) -> list[CostLine]:
    cols = ", ".join(CostLine.model_fields)
    rows = conn.execute(f"SELECT {cols} FROM cost_lines WHERE run_id = %s ORDER BY id", (run_id,))
    return [CostLine.model_validate({**r, "list_price_usd": float(r["list_price_usd"])}) for r in rows]


# --- stories and bibles ---


def save_story(conn: psycopg.Connection[Any], story: Story) -> None:
    conn.execute(
        "INSERT INTO stories (id, story) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET story = EXCLUDED.story",
        (story.id, Jsonb(story.model_dump())),
    )


def story(conn: psycopg.Connection[Any], story_id: str) -> Story:
    row = conn.execute("SELECT story FROM stories WHERE id = %s", (story_id,)).fetchone()
    if row is None:
        raise KeyError(f"no story {story_id}")
    return Story.model_validate(row["story"])


def save_bible(conn: psycopg.Connection[Any], bible: Bible) -> Bible:
    """Persist as the next version for the story and return it with that version."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (bible.story_id,))
        row = conn.execute(
            "SELECT coalesce(max(version), 0) + 1 AS v FROM bibles WHERE story_id = %s", (bible.story_id,)
        ).fetchone()
        saved = bible.model_copy(update={"version": row["v"] if row else 1})
        conn.execute(
            "INSERT INTO bibles (story_id, version, bible) VALUES (%s, %s, %s)",
            (saved.story_id, saved.version, Jsonb(saved.model_dump())),
        )
    return saved


def bible_versions(conn: psycopg.Connection[Any], story_id: str) -> list[Bible]:
    rows = conn.execute("SELECT bible FROM bibles WHERE story_id = %s ORDER BY version", (story_id,))
    return [Bible.model_validate(r["bible"]) for r in rows]


def save_season(conn: psycopg.Connection[Any], source: str, scripts: list[Script]) -> None:
    """Replace the story's season from this source (a new season may have fewer episodes)."""
    with conn.transaction():
        for story_id in {s.story_id for s in scripts}:
            conn.execute("DELETE FROM scripts WHERE story_id = %s AND source = %s", (story_id, source))
        for s in scripts:
            conn.execute(
                "INSERT INTO scripts (story_id, source, episode, script) VALUES (%s, %s, %s, %s)",
                (s.story_id, source, s.episode, Jsonb(s.model_dump())),
            )


def scripts(conn: psycopg.Connection[Any], story_id: str, source: str) -> list[Script]:
    rows = conn.execute(
        "SELECT script FROM scripts WHERE story_id = %s AND source = %s ORDER BY episode", (story_id, source)
    )
    return [Script.model_validate(r["script"]) for r in rows]


# --- decision rows ---


def add_decision(conn: psycopg.Connection[Any], decision: Decision) -> None:
    conn.execute(
        "INSERT INTO decisions (run_id, gate, target, verdict, notes, nudges) VALUES (%s, %s, %s, %s, %s, %s)",
        (
            decision.run_id,
            decision.gate,
            decision.target,
            decision.verdict,
            decision.notes,
            Jsonb([n.model_dump() for n in decision.nudges]),
        ),
    )


def pending_decision(conn: psycopg.Connection[Any], run_id: str, target: str) -> tuple[int, Decision] | None:
    row = conn.execute(
        "SELECT id, run_id, gate, target, verdict, notes, nudges FROM decisions"
        " WHERE run_id = %s AND target = %s AND consumed_at IS NULL ORDER BY id LIMIT 1",
        (run_id, target),
    ).fetchone()
    if row is None:
        return None
    row_id = row.pop("id")
    return row_id, Decision.model_validate(row)


def consume_decision(conn: psycopg.Connection[Any], row_id: int) -> None:
    conn.execute("UPDATE decisions SET consumed_at = now() WHERE id = %s", (row_id,))
