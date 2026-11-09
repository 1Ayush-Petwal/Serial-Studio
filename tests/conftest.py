"""Graph-runner seam harness.

Each test gets an empty Postgres database and a fake network that replays the
recorded gateway cache (tests/fixtures/recordings.jsonl, written by
`serial-studio export-recordings`). Anything unrecorded fails the request, so
the suite never touches the real network.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from serial_studio.gateway import Gateway
from serial_studio.graph import Runner

RECORDINGS = Path(__file__).parent / "fixtures" / "recordings.jsonl"
ADMIN_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://serial:serial@localhost:54329/postgres")


@dataclass
class FakeNetwork:
    """Serves recorded responses by exact request; records every attempt."""

    rows: list[dict[str, Any]]
    requests: list[httpx.Request] = field(default_factory=list)
    override: Callable[[dict[str, Any]], dict[str, Any] | None] = lambda body: None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            for row in self.rows:
                if row["kind"] == "http" and row["request"]["url"] == str(request.url):
                    return httpx.Response(200, text=row["response"]["body"])
        else:
            body = json.loads(request.content)
            if (forced := self.override(body)) is not None:
                return httpx.Response(200, json=forced)
            for row in self.rows:
                if row["kind"] == "model" and row["request"]["body"] == body:
                    return httpx.Response(200, json=row["response"])
        raise httpx.ConnectError(f"network disabled in tests; unrecorded {request.method} {request.url}")

    def model_calls(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if r.method == "POST"]


@dataclass
class App:
    """One 'process': a runner wired to the test database and fake network."""

    runner: Runner
    conn: psycopg.Connection[Any]
    spans: InMemorySpanExporter
    langfuse: Langfuse

    def generations(self) -> list[dict[str, Any]]:
        self.langfuse.flush()
        return [
            dict(s.attributes or {})
            for s in self.spans.get_finished_spans()
            if (s.attributes or {}).get("langfuse.observation.type") == "generation"
        ]


@pytest.fixture
def database_url() -> Iterator[str]:
    name = f"test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    try:
        yield ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def network() -> FakeNetwork:
    rows = [json.loads(line) for line in RECORDINGS.read_text(encoding="utf-8").splitlines()]
    return FakeNetwork(rows)


@pytest.fixture
def make_app(database_url: str, network: FakeNetwork, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., App]]:
    for role in ("JUDGE_MODEL", "WRITER_MODEL"):
        monkeypatch.delenv(role, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    apps: list[App] = []

    def make(gateway_class: type[Gateway] = Gateway) -> App:
        spans = InMemorySpanExporter()
        langfuse = Langfuse(
            public_key=f"pk-lf-test-{uuid.uuid4().hex}",
            secret_key="sk-lf-test",
            base_url="http://127.0.0.1:9",
            span_exporter=spans,
        )
        http = httpx.Client(transport=httpx.MockTransport(network.handle))
        runner = Runner(database_url, http, langfuse, gateway_class)
        app = App(runner, runner.conn, spans, langfuse)
        apps.append(app)
        return app

    yield make
    for app in apps:
        app.langfuse.shutdown()
        app.runner.close()
