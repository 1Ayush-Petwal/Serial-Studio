"""Critique panel: one CrewAI crew behind a typed input and output (decision log: CrewAI for critique).

Four critics (tone, character, structure, ear) and a lead critic who ranks their notes and marks
the must-fix ones. Every crew call goes through the gateway as the judge model, so it is cached,
costed and replayable. Before calibration (#10) scores never gate: only must-fix notes send a
script back.
"""

from __future__ import annotations

import os

# Set before crewai is imported: no telemetry, no trace upload.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from typing import Any  # noqa: E402

from crewai import Agent, BaseLLM, Crew, CrewOutput, Process, Task  # noqa: E402
from crewai.events.listeners.tracing.utils import is_first_execution, mark_first_execution_done  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from serial_studio.gateway import Gateway, role_model  # noqa: E402
from serial_studio.schemas import (  # noqa: E402
    BeatSheet,
    Bible,
    CriticReport,
    CritiqueInput,
    CritiqueNotes,
    LeadReport,
    Message,
    ModelRequest,
    Script,
    SpeakerGuesses,
)

PROMPT_VERSION = "critique-v1"
NARRATOR = "narrator"
CRITICS = ("tone", "character", "structure", "ear")

if is_first_execution():
    # CrewAI otherwise asks on stdin (20 s timeout) whether to upload traces; the answer is no.
    mark_first_execution_done(user_consented=False)


class GatewayLLM(BaseLLM):
    """CrewAI's model hook, routed through the gateway as the judge."""

    def __init__(self, gateway: Gateway, run_id: str) -> None:
        super().__init__(model=role_model("judge").name)
        self._gateway = gateway
        self._run_id = run_id

    def call(
        self,
        messages: Any,
        tools: Any = None,
        callbacks: Any = None,
        available_functions: Any = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        raw = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        response = self._gateway.complete(
            ModelRequest(
                run_id=self._run_id,
                stage="judge",
                node="critique",
                model=role_model("judge"),
                messages=[Message.model_validate({"role": m["role"], "content": m["content"]}) for m in raw],
                params={"temperature": 0, "max_completion_tokens": 2000, "reasoning_effort": "low"},
                prompt_version=PROMPT_VERSION,
            )
        )
        return response.text

    def supports_function_calling(self) -> bool:
        return False


def blind_lines(script: Script) -> list[str]:
    """Dialogue lines numbered, speaker names stripped, for the character critic to attribute."""
    return [f"{i}. {line.text}" for i, line in enumerate(script.lines, 1) if line.speaker != NARRATOR]


def _script_text(script: Script) -> str:
    return "\n".join(f"{line.speaker}: {line.text}" for line in script.lines)


def crew(llm: BaseLLM, inp: CritiqueInput) -> Crew:
    def agent(role: str, goal: str, backstory: str) -> Agent:
        return Agent(role=role, goal=goal, backstory=backstory, llm=llm, allow_delegation=False, verbose=False)

    tone = agent(
        "Tone critic",
        "Judge whether the episode keeps the story's period voice and mood",
        "A radio drama editor who knows Victorian detective fiction.",
    )
    character = agent(
        "Character critic",
        "Tell from the lines alone who is speaking",
        "A casting director: if a listener cannot tell the voices apart on paper, they will not in audio.",
    )
    structure = agent(
        "Structure critic",
        "Check the hook, the beats in order and a cliffhanger that lands on a real event",
        "A serial editor who has cut hundreds of two-minute episodes.",
    )
    ear = agent(
        "Ear critic",
        "Find what will not work heard rather than read",
        "An audio producer: no visual-only beats, short sentences, a balance of narration and dialogue, "
        "names that do not sound alike.",
    )
    lead = agent(
        "Lead critic",
        "Rank every note and mark only those that must be fixed before the editor reads the script",
        "The showrunner. A must-fix note is one a listener would notice; style preferences are not.",
    )
    score = "score: 1 (poor) to 5 (excellent); notes: specific, actionable, quoting the line they mean."
    tasks = [
        Task(
            description=f"Episode {inp.episode} script:\n{{script}}\n\nStory: {{title}}. Judge the tone. {score}",
            expected_output="A score and notes",
            agent=tone,
            output_pydantic=CriticReport,
        ),
        Task(
            description="Cast: {cast}\nDialogue lines with the speaker removed:\n{blind}\n\n"
            "For each line give the cast member you think says it. Then judge how distinct the voices are. " + score,
            expected_output="A guess per line, a score and notes",
            agent=character,
            output_pydantic=SpeakerGuesses,
        ),
        Task(
            description="Beat sheet:\n{beats}\n\nScript:\n{script}\n\nJudge the structure. " + score,
            expected_output="A score and notes",
            agent=structure,
            output_pydantic=CriticReport,
        ),
        Task(
            description="Script:\n{script}\n\nJudge it for the ear. " + score,
            expected_output="A score and notes",
            agent=ear,
            output_pydantic=CriticReport,
        ),
    ]
    tasks.append(
        Task(
            description="Merge the critics' notes into one ranked list (rank 1 = most important), naming the "
            "critic each came from, and mark must_fix only where a listener would notice the problem.",
            expected_output="Ranked notes",
            agent=lead,
            output_pydantic=LeadReport,
            context=list(tasks),
        )
    )
    return Crew(agents=[tone, character, structure, ear, lead], tasks=tasks, process=Process.sequential, verbose=False)


def critique_input(script: Script, sheet: BeatSheet, bible: Bible, title: str) -> CritiqueInput:
    cast = [c.name for c in bible.characters if c.voice_id is not None]
    return CritiqueInput(episode=script.episode, title=title, script=script, beats=sheet.beats, cast=cast)


def critique(gateway: Gateway, run_id: str, inp: CritiqueInput) -> CritiqueNotes:
    """Run the panel. Malformed crew output fails loudly."""
    try:
        result = crew(GatewayLLM(gateway, run_id), inp).kickoff(
            inputs={
                "script": _script_text(inp.script),
                "title": inp.title,
                "cast": ", ".join(inp.cast),
                "blind": "\n".join(blind_lines(inp.script)),
                "beats": "\n".join(f"- {b.kind}: {b.summary}" for b in inp.beats),
            }
        )
    except ValidationError as e:  # a critic's answer did not fit its schema
        raise ValueError(f"critique panel returned malformed output: {e}") from e
    assert isinstance(result, CrewOutput)
    outputs = [t.pydantic for t in result.tasks_output]
    kinds = (CriticReport, SpeakerGuesses, CriticReport, CriticReport, LeadReport)
    if len(outputs) != len(kinds) or not all(isinstance(o, k) for o, k in zip(outputs, kinds, strict=True)):
        raise ValueError(f"critique panel returned malformed output: {[t.raw[:200] for t in result.tasks_output]}")
    reports: list[CriticReport] = outputs[:4]  # type: ignore[assignment]
    guesses: SpeakerGuesses = outputs[1]  # type: ignore[assignment]
    lead: LeadReport = outputs[4]  # type: ignore[assignment]

    truth = [line.speaker for line in inp.script.lines if line.speaker != NARRATOR]
    said = {g.line: g.speaker for g in guesses.guesses}
    numbered = [i for i, line in enumerate(inp.script.lines, 1) if line.speaker != NARRATOR]
    right = sum(said.get(n, "").strip().lower() == who.lower() for n, who in zip(numbered, truth, strict=True))
    scores = {name: float(r.score) for name, r in zip(CRITICS, reports, strict=True)}
    scores["speaker_accuracy"] = round(right / len(truth), 2) if truth else 1.0
    return CritiqueNotes(scores=scores, notes=sorted(lead.notes, key=lambda n: n.rank))
