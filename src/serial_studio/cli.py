"""CLI: start runs and decide gates.

serial-studio run "The Speckled Band" --book 1661
serial-studio show RUN_ID
serial-studio approve RUN_ID           # gates 1-3
serial-studio reject RUN_ID --notes "..."
serial-studio resume RUN_ID            # continue a crashed run
serial-studio baseline "The Speckled Band" --book 1661   # single-prompt season for the A/B test
serial-studio export-recordings PATH   # model cache -> test fixture
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv
from langfuse import Langfuse

from serial_studio import db
from serial_studio.graph import Runner
from serial_studio.ingest import slug
from serial_studio.schemas import Bible, Decision, RunStatus, Script, SeasonPlan, StartRun


def show(status: RunStatus) -> None:
    print(f"run {status.run_id}: {status.state}")
    if status.gate is None:
        return
    print(f"gate {status.gate.gate} waiting on {status.gate.target}\n")
    if status.gate.gate == 1:
        b = Bible.model_validate(status.gate.payload["bible"])
        print("CHARACTERS")
        for c in b.characters:
            print(f"  {c.name}  (aka {', '.join(c.aliases) or '-'})\n    {c.description}")
            for f in c.facts:
                print(f"    - {f}")
        print("PLACES")
        for p in b.places:
            print(f"  {p.name}: {p.description}")
        print("FACTS")
        for f in b.facts:
            print(f"  - {f}")
        print("PRONUNCIATIONS")
        for pr in b.pronunciations:
            print(f"  {pr.term} -> {pr.say_as}")
        print("CLUE LEDGER")
        for cl in b.clues:
            exact = "" if cl.position.exact else " (quote not found verbatim)"
            print(
                f"  [{cl.id}] {cl.kind}: {cl.text}\n    keywords: {', '.join(cl.keywords)}"
                f'\n    scene {cl.position.scene + 1} @ {cl.position.offset}{exact}: "{cl.position.quote}"'
            )
        print("OPEN THREADS")
        for t in b.open_threads:
            print(f"  [{t.id}] {'closed' if t.closed else 'open'}: {t.question}")
    elif status.gate.gate == 2:
        plan = SeasonPlan.model_validate(status.gate.payload["plan"])
        for e in plan.episodes:
            print(f'EPISODE {e.episode}: {e.title}  (from char {e.start}: "{e.starts_at}")')
            if e.recap:
                print(f"  recap: {e.recap}")
            for k in e.listener_knows:
                print(f"  knows: {k}")
            for beat in e.beats:
                clues = f"  [plants {', '.join(beat.clue_ids)}]" if beat.clue_ids else ""
                print(f"  {beat.kind}: {beat.summary}{clues}")
            if e.cliffhanger:
                print(f"  cliffhanger event: {e.cliffhanger.event}  (keywords: {', '.join(e.cliffhanger.keywords)})")
            if e.reveals:
                print(f"  reveals: {', '.join(e.reveals)}")
        print("CASTING")
        for name, voice in plan.casting.items():
            print(f"  {name}: {voice}")
    elif status.gate.gate == 3:
        g3 = status.gate.payload
        script = Script.model_validate(g3["script"])
        words = sum(len(line.text.split()) for line in script.lines)
        print(f"EPISODE {script.episode}: {script.title}  (bible v{script.bible_version})\n  {script.blurb}")
        print(f"  {words} words, predicted {g3['predicted_seconds']} s, {g3['revisions']} revision(s)\n")
        for line in g3["markup"]:
            print(f"  {line}")
        for f in g3["fixes"]:
            print(f"  auto-fixed: {f}")
        for v in g3["violations"]:
            print(f"  VIOLATION {v['rule']}: {v['message']}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    p = argparse.ArgumentParser(prog="serial-studio")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "baseline"):
        run = sub.add_parser(name)
        run.add_argument("title")
        run.add_argument("--book", type=int, required=True, help="Gutenberg book id containing the story")
    for name in ("show", "approve", "resume"):
        sub.add_parser(name).add_argument("run_id")
    rej = sub.add_parser("reject")
    rej.add_argument("run_id")
    rej.add_argument("--notes", required=True)
    sub.add_parser("export-recordings").add_argument("path")
    args = p.parse_args(argv)

    if args.cmd == "export-recordings":
        conn = db.connect(os.environ["DATABASE_URL"])
        db.setup(conn)
        with open(args.path, "w", encoding="utf-8") as f:
            for row in db.cache_rows(conn):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return

    langfuse = Langfuse()
    # Free-tier Gemini can queue a long planning call for many minutes before answering.
    http = httpx.Client(timeout=httpx.Timeout(900, connect=30), follow_redirects=True)
    runner = Runner(os.environ["DATABASE_URL"], http, langfuse)
    try:
        if args.cmd == "baseline":
            run_id = runner.baseline(StartRun(title=args.title, book_id=args.book))
            for sc in db.scripts(runner.conn, slug(args.title), "baseline"):
                words = sum(len(line.text.split()) for line in sc.lines)
                print(f"EPISODE {sc.episode}: {sc.title}  ({words} words)\n  {sc.blurb}")
                for line in sc.lines:
                    print(f"  {line.speaker}: {line.text}")
            print(f"run {run_id}: baseline stored")
            return
        if args.cmd == "run":
            status = runner.start(StartRun(title=args.title, book_id=args.book))
        elif args.cmd == "show":
            status = runner.status(args.run_id)
        elif args.cmd == "resume":
            status = runner.resume(args.run_id)
        else:
            status = runner.decide(_decision(runner.status(args.run_id), args))
        show(status)
    finally:
        langfuse.flush()
        runner.close()


def _decision(status: RunStatus, args: Any) -> Decision:
    if status.gate is None:
        sys.exit(f"run {status.run_id} is not waiting at a gate ({status.state})")
    return Decision(
        run_id=status.run_id,
        gate=status.gate.gate,
        target=status.gate.target,
        verdict="approve" if args.cmd == "approve" else "reject",
        notes=getattr(args, "notes", ""),
    )


if __name__ == "__main__":
    main()
