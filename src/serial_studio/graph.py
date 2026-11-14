"""Graph runner: LangGraph flow, Postgres checkpointer and the generic gate.

Every gate works the same way: the node interrupts with a GatePayload, a
decision row is written (CLI now, review page later), and resume() feeds that
row back into the paused node.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

import httpx
import psycopg
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import START, StateGraph
from langgraph.types import Command, Send, interrupt
from pydantic import BaseModel

from serial_studio import baseline, beat_planner, db, schemas, screenplay, story_architect
from serial_studio.gateway import Gateway
from serial_studio.ingest import ingest, scenes
from serial_studio.schemas import (
    ArchitectInput,
    Bible,
    Decision,
    Drafted,
    GatePayload,
    PlannerInput,
    RunStatus,
    Scene,
    ScreenplayInput,
    SeasonPlan,
    StartRun,
    Story,
)


def _merge(old: dict[int, Drafted], new: dict[int, Drafted]) -> dict[int, Drafted]:
    return {**old, **new}


class RunState(BaseModel):
    run_id: str
    start: StartRun
    story: Story | None = None
    scenes: list[Scene] = []
    scene_index: int = 0
    bible: Bible | None = None
    notes: str | None = None  # gate-1 notes for the Story Architect
    bible_approved: bool = False
    plan: SeasonPlan | None = None
    plan_notes: str | None = None  # gate-2 notes for the Beat Planner
    plan_approved: bool = False
    episode: int = 0  # the episode a write_episode branch drafts
    drafts: Annotated[dict[int, Drafted], _merge] = {}
    approved: int = 0  # episodes approved so far; approval is strictly in order
    script_versions: dict[int, int] = {}  # times each episode has been shown at gate 3
    script_notes: dict[int, str] = {}  # gate-3 notes per episode for the Screenplay agent
    rejected: bool = False  # the last gate-3 decision sent the episode back

    def season(self) -> list[Drafted]:
        return [self.drafts[n] for n in sorted(self.drafts)]


def review(d: Drafted) -> dict[str, Any]:
    """What gate 3 shows for one draft."""
    return {
        "episode": d.episode,
        "script": d.script.model_dump(),
        "markup": screenplay.markup(d.script),
        "predicted_seconds": screenplay.predicted_seconds(d.script),
        "violations": [v.model_dump() for v in d.violations],
        "fixes": d.fixes,
        "revisions": d.revisions,
    }


def gate(conn: psycopg.Connection[Any], payload: GatePayload) -> Decision:
    """Pause until a decision row for this target is fed back by resume()."""
    resumed = interrupt(payload.model_dump())
    decision = Decision.model_validate(resumed["decision"])
    if (decision.gate, decision.target) != (payload.gate, payload.target):
        raise ValueError(f"decision for {decision.target} fed to gate on {payload.target}")
    db.consume_decision(conn, resumed["row_id"])
    return decision


def build(conn: psycopg.Connection[Any], gateway: Gateway) -> StateGraph[RunState]:
    def ingest_node(s: RunState) -> dict[str, Any]:
        story = ingest(gateway, s.start)
        db.save_story(conn, story)
        return {"story": story, "scenes": scenes(story.text), "bible": Bible(story_id=story.id)}

    def architect_node(s: RunState) -> dict[str, Any]:
        assert s.bible is not None
        scene = s.scenes[s.scene_index]
        inp = ArchitectInput(story_id=s.bible.story_id, scene=scene, bible=s.bible, notes=s.notes)
        delta = story_architect.extract(gateway, s.run_id, inp, len(s.scenes))
        return {"bible": story_architect.merge(s.bible, delta, scene), "scene_index": s.scene_index + 1}

    def save_bible_node(s: RunState) -> dict[str, Any]:
        assert s.bible is not None
        return {"bible": db.save_bible(conn, story_architect.finalize(s.bible))}

    def gate_1_node(s: RunState) -> dict[str, Any]:
        assert s.bible is not None
        payload = GatePayload(
            gate=1,
            run_id=s.run_id,
            target=f"bible:{s.bible.story_id}:v{s.bible.version}",
            payload={"bible": s.bible.model_dump()},
        )
        decision = gate(conn, payload)
        if decision.verdict == "approve":
            return {"bible_approved": True}
        # Reject: the Story Architect re-extracts from scratch with the editor's notes. Earlier notes
        # are kept: extraction is sampled, so a fresh pass can drop what a previous note fixed.
        notes = "\n".join(n for n in (s.notes, decision.notes) if n)
        return {"notes": notes, "scene_index": 0, "bible": Bible(story_id=s.bible.story_id)}

    def beat_planner_node(s: RunState) -> dict[str, Any]:
        assert s.story is not None and s.bible is not None
        inp = PlannerInput(story=s.story, bible=s.bible, notes=s.plan_notes)
        version = s.plan.version + 1 if s.plan else 1
        return {"plan": beat_planner.plan(gateway, s.run_id, inp, version)}

    def gate_2_node(s: RunState) -> dict[str, Any]:
        assert s.plan is not None
        payload = GatePayload(
            gate=2,
            run_id=s.run_id,
            target=f"season-plan:{s.plan.story_id}:v{s.plan.version}",
            payload={"plan": s.plan.model_dump()},
        )
        decision = gate(conn, payload)
        if decision.verdict == "approve":
            return {"plan_approved": True}
        return {"plan_notes": "\n".join(n for n in (s.plan_notes, decision.notes) if n)}

    def cast_node(s: RunState) -> dict[str, Any]:
        # The approved casting and clue episodes become a new bible version (one writer of truth).
        assert s.bible is not None and s.plan is not None
        return {"bible": db.save_bible(conn, story_architect.cast(s.bible, s.plan))}

    def screenplay_input(s: RunState, episode: int) -> ScreenplayInput:
        assert s.story is not None and s.bible is not None and s.plan is not None
        notes = s.script_notes.get(episode)
        return ScreenplayInput(story=s.story, bible=s.bible, plan=s.plan, episode=episode, notes=notes)

    def fan_out(s: RunState) -> list[Send]:
        # One branch per episode; the season drafts in parallel against the same bible and plan.
        assert s.plan is not None
        return [Send("write_episode", s.model_copy(update={"episode": e.episode})) for e in s.plan.episodes]

    def write_episode_node(s: RunState) -> dict[str, Any]:
        return {"drafts": {s.episode: screenplay.write_episode(gateway, s.run_id, screenplay_input(s, s.episode))}}

    def gate_3_node(s: RunState) -> dict[str, Any]:
        """Every draft is readable; only the next episode in order can be approved."""
        assert s.bible is not None
        n = s.approved + 1
        d = s.drafts[n]
        version = s.script_versions.get(n, 0) + 1
        payload = GatePayload(
            gate=3,
            run_id=s.run_id,
            target=f"script:{s.bible.story_id}:ep{n}:v{version}",
            payload={**review(d), "season": [review(x) | {"approved": x.episode <= s.approved} for x in s.season()]},
        )
        decision = gate(conn, payload)
        versions = s.script_versions | {n: version}
        if decision.verdict == "approve":
            return {"approved": n, "script_versions": versions, "rejected": False}
        notes = "\n".join(x for x in (s.script_notes.get(n), decision.notes) if x)
        return {"script_notes": s.script_notes | {n: notes}, "script_versions": versions, "rejected": True}

    def rewrite_node(s: RunState) -> dict[str, Any]:
        n = s.approved + 1
        return {"drafts": {n: screenplay.write_episode(gateway, s.run_id, screenplay_input(s, n))}}

    def reconcile_node(s: RunState) -> dict[str, Any]:
        """Record what the approved episode established, then hold every later draft to it."""
        assert s.bible is not None and s.plan is not None
        n = s.approved
        script = s.drafts[n].script
        last = n == len(s.plan.episodes)
        record = story_architect.record(gateway, s.run_id, script, s.plan.episodes[n - 1], last)
        bible = db.save_bible(conn, s.bible.model_copy(update={"episodes": [*s.bible.episodes, record]}))
        db.save_script(conn, "pipeline", script)
        later = s.model_copy(update={"bible": bible})
        drafts = {
            d.episode: screenplay.write_episode(gateway, s.run_id, screenplay_input(later, d.episode), previous=d)
            for d in s.season()
            if d.episode > n
        }
        return {"bible": bible, "drafts": drafts}

    def after_gate_3(s: RunState) -> Literal["reconcile", "rewrite"]:
        return "rewrite" if s.rejected else "reconcile"

    def after_reconcile(s: RunState) -> Literal["gate_3", "__end__"]:
        assert s.plan is not None
        return "__end__" if s.approved == len(s.plan.episodes) else "gate_3"

    def after_architect(s: RunState) -> Literal["story_architect", "save_bible"]:
        return "story_architect" if s.scene_index < len(s.scenes) else "save_bible"

    def after_gate_1(s: RunState) -> Literal["beat_planner", "story_architect"]:
        return "beat_planner" if s.bible_approved else "story_architect"

    def after_gate_2(s: RunState) -> Literal["cast", "beat_planner"]:
        return "cast" if s.plan_approved else "beat_planner"

    g = StateGraph(RunState)
    g.add_node("ingest", ingest_node)
    g.add_node("story_architect", architect_node)
    g.add_node("save_bible", save_bible_node)
    g.add_node("gate_1", gate_1_node)
    g.add_node("beat_planner", beat_planner_node)
    g.add_node("gate_2", gate_2_node)
    g.add_node("cast", cast_node)
    g.add_node("write_episode", write_episode_node)
    g.add_node("gate_3", gate_3_node)
    g.add_node("rewrite", rewrite_node)
    g.add_node("reconcile", reconcile_node)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "story_architect")
    g.add_conditional_edges("story_architect", after_architect)
    g.add_edge("save_bible", "gate_1")
    g.add_conditional_edges("gate_1", after_gate_1)
    g.add_edge("beat_planner", "gate_2")
    g.add_conditional_edges("gate_2", after_gate_2)
    g.add_conditional_edges("cast", fan_out, ["write_episode"])
    g.add_edge("write_episode", "gate_3")
    g.add_conditional_edges("gate_3", after_gate_3)
    g.add_edge("rewrite", "gate_3")
    g.add_conditional_edges("reconcile", after_reconcile)
    return g


class Runner:
    """Start a run, then resume it after a crash or once a decision row exists."""

    def __init__(
        self, database_url: str, http: httpx.Client, langfuse: Langfuse, gateway_class: type[Gateway] = Gateway
    ) -> None:
        self.conn = db.connect(database_url)

        # The checkpointer pipelines its writes, so it gets a connection of its own.
        self._checkpoint_conn = db.connect(database_url)

        # Strict allowlist: checkpoints may only rebuild our own schema types.
        allowed = [t for t in vars(schemas).values() if isinstance(t, type) and issubclass(t, BaseModel)]
        checkpointer = PostgresSaver(self._checkpoint_conn, serde=JsonPlusSerializer(allowed_msgpack_modules=allowed))
        checkpointer.setup()
        db.setup(self.conn)
        self.gateway = gateway_class(self.conn, http, langfuse)
        self.graph = build(self.conn, self.gateway).compile(checkpointer=checkpointer)

    def close(self) -> None:
        self.conn.close()
        self._checkpoint_conn.close()

    def _config(self, run_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": run_id}, "recursion_limit": 200}

    def start(self, start: StartRun) -> RunStatus:
        run_id = uuid.uuid4().hex[:12]
        self.graph.invoke(RunState(run_id=run_id, start=start), self._config(run_id))
        return self.status(run_id)

    def baseline(self, start: StartRun) -> str:
        """Single-prompt season for the A/B test; outside the graph, since it has no gates."""
        run_id = "baseline-" + uuid.uuid4().hex[:12]
        story = ingest(self.gateway, start)
        db.save_story(self.conn, story)
        db.save_season(self.conn, "baseline", baseline.generate(self.gateway, run_id, story))
        return run_id

    def status(self, run_id: str) -> RunStatus:
        snap = self.graph.get_state(self._config(run_id))
        if not snap.created_at:
            raise KeyError(f"no run {run_id}")
        if snap.interrupts:
            return RunStatus(run_id=run_id, state="paused", gate=GatePayload.model_validate(snap.interrupts[0].value))
        return RunStatus(run_id=run_id, state="stopped" if snap.next else "done")

    def decide(self, decision: Decision) -> RunStatus:
        """Write a decision row (what the review page will do), then resume."""
        open_gate = self.status(decision.run_id).gate
        if open_gate is None or (open_gate.gate, open_gate.target) != (decision.gate, decision.target):
            raise ValueError(f"run {decision.run_id} is not waiting on {decision.target}")
        db.add_decision(self.conn, decision)
        return self.resume(decision.run_id)

    def resume(self, run_id: str) -> RunStatus:
        config = self._config(run_id)
        snap = self.graph.get_state(config)
        if snap.interrupts:
            gate_payload = GatePayload.model_validate(snap.interrupts[0].value)
            pending = db.pending_decision(self.conn, run_id, gate_payload.target)
            if pending is None:
                return self.status(run_id)  # still waiting on the editor
            row_id, decision = pending
            self.graph.invoke(Command(resume={"row_id": row_id, "decision": decision.model_dump()}), config)
        elif snap.next:
            self.graph.invoke(None, config)  # crashed mid-way: continue from the last checkpoint
        return self.status(run_id)
