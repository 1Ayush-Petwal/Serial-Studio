"""Single-prompt baseline: the whole story to a season of scripts in one writer call.

Same writer model and script schema as the pipeline, none of its planning,
validation or critique, so the A/B test measures what the pipeline adds. The
only repair is for malformed JSON: a baseline that cannot be parsed compares
nothing.
"""

from __future__ import annotations

from pydantic import ValidationError

from serial_studio.gateway import Gateway, role_model, strict_schema
from serial_studio.schemas import BaselineDraft, Message, ModelRequest, Script, Story

PROMPT_VERSION = "baseline-v1"
MAX_REPAIRS = 2

SYSTEM = """Adapt this mystery short story into an audio serial: a season of 5-7 episodes (target 6),
each about 260 spoken words and never more than 300, so it runs under 2 minutes.
Write narration with light dialogue for the ear. Each line has a speaker: "narrator" or a
character's name. End every episode but the last on a cliffhanger. Give each episode a title
and a one-sentence blurb."""

SCHEMA = strict_schema(BaselineDraft)


def generate(gateway: Gateway, run_id: str, story: Story) -> list[Script]:
    messages = [
        Message(role="system", content=SYSTEM),
        Message(role="user", content=f"{story.title} by {story.author}\n<<<\n{story.text}\n>>>"),
    ]
    for _ in range(MAX_REPAIRS + 1):
        response = gateway.complete(
            ModelRequest(
                run_id=run_id,
                stage="text",
                node="baseline",
                model=role_model("writer"),
                messages=messages,
                prompt_version=PROMPT_VERSION,
                response_schema=SCHEMA,
            )
        )
        try:
            draft = BaselineDraft.model_validate_json(response.text)
        except ValidationError as e:
            errors = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
            messages += [
                Message(role="assistant", content=response.text),
                Message(role="user", content="Return valid JSON for the schema. Errors:\n- " + "\n- ".join(errors)),
            ]
            continue
        return [
            Script(
                story_id=story.id,
                episode=i,
                bible_version=None,
                title=e.title,
                blurb=e.blurb,
                lines=e.lines,
                clue_spans=[],
                cues=[],
            )
            for i, e in enumerate(draft.episodes, 1)
        ]
    raise ValueError(f"baseline returned malformed JSON after {MAX_REPAIRS} repairs: {errors}")
