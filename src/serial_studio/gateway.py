"""Model gateway: the single path for every external call.

Every call is cached by its exact wire request plus prompt version, so a re-run
is free and the cache doubles as the record/replay store for tests. Model calls
also write a shadow-cost line and a Langfuse generation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import tomllib
from importlib.resources import files
from typing import Any

import httpx
import psycopg
from langfuse import Langfuse, propagate_attributes

from serial_studio import db
from serial_studio.schemas import CostLine, ModelRef, ModelRequest, ModelResponse

REGISTRY: dict[str, Any] = tomllib.loads(files("serial_studio").joinpath("models.toml").read_text())
MAX_RETRY_WAIT_S = 120  # a longer Retry-After means a daily quota is spent: fail instead of hanging


class GatewayError(RuntimeError):
    pass


def role_model(role: str) -> ModelRef:
    """Model for a role ("judge", "writer"): env var <ROLE>_MODEL, else models.toml [roles]."""
    ref = os.environ.get(f"{role.upper()}_MODEL") or REGISTRY["roles"][role]
    if ref not in REGISTRY["models"]:
        raise GatewayError(f"{ref!r} has no entry in models.toml (needed for list price)")
    return ModelRef.parse(ref)


def _key(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


class Gateway:
    def __init__(self, conn: psycopg.Connection[Any], http: httpx.Client, langfuse: Langfuse) -> None:
        self.conn = conn
        self.http = http
        self.langfuse = langfuse

    def fetch(self, url: str) -> str:
        """Cached GET for non-model sources (Gutendex). No cost line, no trace."""
        request = {"kind": "http", "url": url}
        key = _key(request)
        if (hit := db.cache_get(self.conn, key)) is not None:
            return str(hit["body"])
        body = self._send("GET", url).text
        db.cache_put(self.conn, key, "http", request, {"body": body})
        return body

    def complete(self, req: ModelRequest) -> ModelResponse:
        spec = REGISTRY["models"][str(req.model)]
        body: dict[str, Any] = {
            "model": req.model.name,
            "messages": [m.model_dump() for m in req.messages],
            **req.params,
        }
        if req.response_schema is not None:
            body["response_format"] = (
                {
                    "type": "json_schema",
                    "json_schema": {"name": "output", "schema": req.response_schema, "strict": True},
                }
                if spec["json_schema"]
                else {"type": "json_object"}
            )
        request = {"kind": "model", "provider": req.model.provider, "body": body, "prompt_version": req.prompt_version}
        key = _key(request)

        with (
            self.langfuse.start_as_current_observation(
                name=req.node,
                as_type="generation",
                model=str(req.model),
                input=body["messages"],
                model_parameters=req.params,
                version=req.prompt_version,
            ) as generation,
            propagate_attributes(session_id=req.run_id, metadata={"stage": req.stage}),
        ):
            data = db.cache_get(self.conn, key)
            cache_hit = data is not None
            if data is None:
                data = self._post_chat(req.model, body)
                db.cache_put(self.conn, key, "model", request, data)

            usage = data["usage"]
            in_tok, out_tok = int(usage["prompt_tokens"]), int(usage["completion_tokens"])
            price = (in_tok * spec["input_per_mtok"] + out_tok * spec["output_per_mtok"]) / 1e6
            text = data["choices"][0]["message"]["content"] or ""
            db.add_cost_line(
                self.conn,
                CostLine(
                    run_id=req.run_id,
                    stage=req.stage,
                    node=req.node,
                    provider=req.model.provider,
                    model=req.model.name,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    list_price_usd=price,
                    cache_hit=cache_hit,
                ),
            )
            generation.update(
                output=text,
                usage_details={"input": in_tok, "output": out_tok},
                cost_details={"total": price},
                metadata={"cache_hit": cache_hit, "run_id": req.run_id},
            )
        return ModelResponse(text=text, input_tokens=in_tok, output_tokens=out_tok, cache_hit=cache_hit)

    def _post_chat(self, model: ModelRef, body: dict[str, Any]) -> dict[str, Any]:
        provider = REGISTRY["providers"][model.provider]
        api_key = os.environ.get(provider["key_env"])
        if not api_key:
            raise GatewayError(f"{provider['key_env']} is not set (see .env.example)")
        r = self._send(
            "POST",
            provider["base_url"] + "/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data: dict[str, Any] = r.json()
        return data

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Retry rate limits and server errors; anything else fails loudly."""
        for attempt in range(8):
            r = self.http.request(method, url, **kwargs)
            # Groq validates structured output after generating it (best-effort, not constrained),
            # so a schema miss is a 400 worth a couple of fresh samples.
            if r.status_code == 400 and "json_validate_failed" in r.text and attempt < 2:
                continue
            if r.status_code != 429 and r.status_code < 500:
                if r.is_error:
                    raise GatewayError(f"{method} {url} -> {r.status_code}: {r.text[:1000]}")
                return r
            wait = float(r.headers.get("retry-after") or 2**attempt)
            if wait > MAX_RETRY_WAIT_S:
                raise GatewayError(f"{method} {url} -> {r.status_code}, retry-after {wait}s: {r.text[:500]}")
            time.sleep(wait)
        raise GatewayError(f"{method} {url} still failing after retries: {r.status_code} {r.text[:500]}")
