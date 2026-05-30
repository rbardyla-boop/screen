"""
vault_intelligence.py — Dispatcher and core gap-detection engine.

Actual implementations live in:
  vault_ai.py     — link, promote, inbox, connections, ask, write-prep, contradict, synthesize
  vault_graph.py  — graph-analyze
  vault_skills.py — skill-capture, skill-log, skill-from-memopipe, skill-audit, swarm-dashboard

Commands
--------

  gaps [--scope Memory] [--paths "foo,bar"]
      Scans high-signal locations for open loops.
      Loops unseen for 14+ days surface under EVAPORATING at the top of the dashboard.
      Writes Memory/Unfinished Work Dashboard.md.

  link <path/to/note.md>
      Finds 3-5 semantically related notes and appends an AI Suggested Connections section.

  promote
      Interactive: pick an item from Open-Loops.md and promote it as a Project, Concept,
      or Literature source.

  inbox
      Process markdown files in 00_Inbox/.

  connections [--days 7]
      Finds non-obvious connections between recently modified Memory/ notes and the vault.

  ask "<question>"
      Answers a question by searching vault notes first.

  write-prep "<topic>"
      Scans vault and produces a writing prep doc in Memory/Outputs/.

  contradict
      Surfaces contradictory positions across permanent/Memory notes.

  synthesize "<topic>"
      Synthesizes all vault notes on a topic into Memory/Outputs/.

  skill-capture [raw text...]
      Convert raw text into a SKILL.md in Memory/Skills/.

  skill-log <slug> "<observation>"
      Append an observation to a skill's .memory.md and update last_used.

  skill-from-memopipe [hours]
      Detect repeatable skill patterns in recent MemoPipe captures.

  skill-audit <slug>
      Run debt-prevention audit on a skill draft.

  swarm-dashboard
      Compute colony state and write Memory/Swarm-Dashboard.md.

  graph-analyze [--scope Memory|vault] [--top N]
      Build the wikilink graph and write a hub/orphan/cluster report.

  auto-link-orphans [--scope Memory] [--max 3]
      Link the N most-recently-modified orphaned notes. Run daily to shrink orphan rate.

Usage examples
--------------
  python vault_intelligence.py gaps
  python vault_intelligence.py gaps --scope Memory
  python vault_intelligence.py link "Memory/Active Projects/some-project.md"
  python vault_intelligence.py promote
  python vault_intelligence.py inbox
  python vault_intelligence.py connections --days 14
  python vault_intelligence.py ask "what do I think about attention mechanisms"
  python vault_intelligence.py write-prep "transformer architectures"
  python vault_intelligence.py contradict
  python vault_intelligence.py synthesize "machine learning"
  python vault_intelligence.py graph-analyze
  python vault_intelligence.py graph-analyze --scope Memory --top 10
  python vault_intelligence.py swarm-dashboard
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ai_provider import ask_ai

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")

HIGH_SIGNAL_GAP_PATTERNS: list[str] = [
    r"\bTODO[:\s]",
    r"\bFIXME[:\s]",
    r"\bTBD[:\s]",
    r"\bWIP[:\s]",
    r"#open-loop",
    r"\[\[TODO\]\]",
    r"OPEN LOOP",
    r"left this hanging",
    r"never finished",
    r"still need to (actually|really|properly)",
]

LOOSE_GAP_PATTERNS: list[str] = [
    r"\bneed to\b",
    r"\bshould (really|actually)\b",
    r"look into this",
    r"figure this out",
]

HIGH_RE = re.compile("|".join(HIGH_SIGNAL_GAP_PATTERNS), re.IGNORECASE)
LOOSE_RE = re.compile("|".join(LOOSE_GAP_PATTERNS), re.IGNORECASE)

NEVER_SCAN_SUBSTRINGS = [
    "/grok/",
    "/00_Inbox/grok",
    "/venv/",
    "/node_modules/",
    "/.git/",
    "/dist/",
    "/build/",
    "/target/",
    "/__pycache__/",
    "VocalCoach",
    "youtube_system",
]


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _should_skip_path(p: Path, vault: Path) -> bool:
    try:
        rel = str(p.relative_to(vault)).lower()
    except ValueError:
        rel = str(p).lower()
    return any(bad.lower() in rel for bad in NEVER_SCAN_SUBSTRINGS)


def _is_real_open_loop_line(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 280:
        return False
    if HIGH_RE.search(line):
        return True
    if LOOSE_RE.search(line):
        if len(line) < 140 and any(
            kw in line.lower()
            for kw in ["project", "need to", "should", "figure", "look into", "finish", "complete"]
        ):
            return True
    if "#open-loop" in line.lower() or "[[todo]]" in line.lower():
        return True
    return False


# ---------------------------------------------------------------------------
# Stale-loop age tracking
# ---------------------------------------------------------------------------

def _gap_fingerprint(gap: str) -> str:
    return hashlib.md5(gap.encode("utf-8", errors="replace")).hexdigest()[:12]


def _load_loop_state() -> dict[str, str]:
    """Load {fingerprint: first_seen_date} from Memory/.loop-state.json."""
    p = Path(VAULT_PATH) / "Memory" / ".loop-state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_loop_state(state: dict[str, str]) -> None:
    p = Path(VAULT_PATH) / "Memory" / ".loop-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

def collect_gaps(scopes: list[str]) -> list[str]:
    vault = Path(VAULT_PATH)
    gaps: list[str] = []
    seen: set[str] = set()

    search_roots: list[Path] = []
    for scope in scopes:
        scope = scope.strip()
        if not scope:
            continue
        if scope.lower() in {"memory", "core"}:
            search_roots.append(vault / "Memory")
        elif scope.lower() in {"active", "projects"}:
            search_roots.append(vault / "Memory/Active Projects")
            if (vault / "Active Projects").exists():
                search_roots.append(vault / "Active Projects")
        else:
            candidate = vault / scope
            if candidate.exists():
                search_roots.append(candidate)

    if not search_roots:
        mem = vault / "Memory"
        if mem.exists():
            search_roots = [mem]
        else:
            print("No Memory/ folder found. Create it or pass explicit --paths.")
            return []

    for root in search_roots:
        if not root.exists():
            continue
        for md in sorted(root.rglob("*.md")):
            if _should_skip_path(md, vault):
                continue
            if md.name == "Unfinished Work Dashboard.md":
                continue
            if "Archive" in md.parts:
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = md.relative_to(vault)
            for line in text.splitlines():
                if _is_real_open_loop_line(line):
                    key = f"{rel}::{line.strip()[:80]}"
                    if key not in seen:
                        seen.add(key)
                        gaps.append(f"[[{rel}]] — {line.strip()}")
            name_lower = md.name.lower()
            if any(x in name_lower for x in ["todo", "open loop", "unfinished", "hanging", "wip"]):
                key = f"FILE::{rel}"
                if key not in seen:
                    seen.add(key)
                    gaps.append(f"[[{rel}]] — (note titled as open work)")

    # Stale skill detection — surfaces in the dashboard automatically.
    skills_dir = vault / "Memory" / "Skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_path = skill_dir / "SKILL.md"
            if not skill_path.exists():
                continue
            try:
                text = skill_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            m = re.search(r"last_used: (\d{4}-\d{2}-\d{2})", text)
            if m:
                try:
                    last_used = datetime.strptime(m.group(1), "%Y-%m-%d")
                    age_days = (datetime.now() - last_used).days
                    if age_days > 30:
                        key = f"SKILL::{skill_dir.name}"
                        if key not in seen:
                            seen.add(key)
                            gaps.append(
                                f"[[Memory/Skills/{skill_dir.name}/SKILL.md]] — "
                                f"SKILL DEBT: not used in {age_days} days (use it or kill it)"
                            )
                except ValueError:
                    continue

    return gaps[:200]


def run_gaps(scope_arg: str | None = None, paths_arg: str | None = None) -> None:
    vault = Path(VAULT_PATH)

    if paths_arg:
        scopes = [p.strip() for p in paths_arg.split(",")]
    elif scope_arg:
        scopes = [scope_arg]
    else:
        scopes = ["Memory"]

    print(f"Scanning for open loops in scopes: {scopes}")
    gaps = collect_gaps(scopes)

    if not gaps:
        print("No high-signal open loops found. Add TODO:, #open-loop, or short task lines.")
        return

    # ── stale-loop age tracking ──────────────────────────────────────────────
    today_str = datetime.now().strftime("%Y-%m-%d")
    state = _load_loop_state()
    current_fps: dict[str, str] = {_gap_fingerprint(g): g for g in gaps}

    # Carry forward first-seen dates; stamp genuinely new loops with today
    new_state: dict[str, str] = {fp: state.get(fp, today_str) for fp in current_fps}
    _save_loop_state(new_state)

    evaporating: list[str] = []
    fresh: list[str] = []
    for fp, gap in current_fps.items():
        try:
            age = (datetime.now() - datetime.strptime(new_state[fp], "%Y-%m-%d")).days
        except ValueError:
            age = 0
        if age >= 14:
            evaporating.append(f"[EVAPORATING — {age}d] {gap}")
        else:
            fresh.append(gap)

    sections: list[str] = []
    if evaporating:
        sections.append(
            "=== EVAPORATING (unseen 14+ days — need a decision NOW) ===\n"
            + "\n".join(evaporating)
        )
    if fresh:
        sections.append("=== ACTIVE ===\n" + "\n".join(fresh))
    joined = "\n\n".join(sections)

    evap_instruction = (
        "\n\nCRITICAL: Items marked [EVAPORATING] have been unresolved for 14+ days. "
        "Place ALL of them under a prominent '## EVAPORATING' section at the TOP of the dashboard, "
        "BEFORE all other sections. These are the user's core failure mode — they must be killed or committed to."
        if evaporating else ""
    )

    prompt = (
        "You are the user's ruthless memory prosthetic.\n"
        "The user has severe 'start ambitious projects and then completely forget they exist' syndrome.\n"
        "Below are the ONLY unfinished items that passed very strict filters from their high-signal Memory core.\n\n"
        "Your job:\n"
        "- Group by real project/theme (be aggressive about merging duplicates)\n"
        "- For each item, decide if it is still alive or should be killed\n"
        "- Output a clean, cold, actionable Obsidian Markdown dashboard\n"
        "- Use ## for themes, bullets for items\n"
        "- Keep [[wikilinks]] clickable\n"
        "- At the end add a tiny 'Merciless Recommendations' section with 3-5 concrete decisions the user should make this week"
        f"{evap_instruction}\n\n"
        f"Open loops:\n{joined}"
    )

    print(
        f"Found {len(gaps)} high-signal items "
        f"({len(evaporating)} evaporating). Asking AI to build the dashboard…"
    )
    dashboard = ask_ai(prompt)

    out = vault / "Memory/Unfinished Work Dashboard.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Unfinished Work Dashboard\n\n{dashboard}\n", encoding="utf-8")
    print(f"Dashboard written: {out}")
    print("Open it in Obsidian. This is now your primary memory surface.")


# ---------------------------------------------------------------------------
# Auto-link orphans (daily habit — reduces the 98%-orphan problem over time)
# ---------------------------------------------------------------------------

def run_auto_link_orphans(scope: str = "Memory", max_links: int = 3) -> None:
    """Link the N most-recently-modified orphaned notes in the given scope."""
    from vault_graph import _build_link_graph, _compute_graph_stats
    from vault_ai import run_link

    vault = Path(VAULT_PATH)
    scan_root = vault / scope if scope.lower() not in {"vault", "all"} else vault

    if not scan_root.exists():
        print(f"Scope path not found: {scan_root}")
        return

    graph, _ = _build_link_graph(scan_root, vault)
    stats = _compute_graph_stats(graph)
    orphan_rel_paths: list[str] = stats["orphans"]

    if not orphan_rel_paths:
        print(f"No orphaned notes in {scope}/. Great.")
        return

    orphan_paths_sorted = sorted(
        [(vault / f"{rel}.md") for rel in orphan_rel_paths if (vault / f"{rel}.md").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    candidates = orphan_paths_sorted[:max_links]
    print(
        f"Auto-linking {len(candidates)} of {len(orphan_rel_paths)} orphaned notes "
        f"(scope={scope}, cap={max_links}/day)…"
    )

    for note_path in candidates:
        rel = str(note_path.relative_to(vault))
        print(f"  → {rel}")
        try:
            run_link(str(note_path.relative_to(vault)))
        except Exception as e:
            print(f"    [skip] {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not VAULT_PATH:
        print("Error: VAULT_PATH is not set in .env")
        sys.exit(1)

    try:
        from vault_guard import run_audit
        code = run_audit(strict=False)
        if code >= 2:
            print("\n[GUARD] CRITICAL: Vault health check failed. Fix violations first.")
            sys.exit(2)
    except Exception:
        print("[GUARD] Could not load vault_guard (proceeding anyway)")

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "gaps":
        scope = None
        paths = None
        for i, arg in enumerate(sys.argv[2:], 2):
            if arg == "--scope" and i + 1 < len(sys.argv):
                scope = sys.argv[i + 1]
            elif arg == "--paths" and i + 1 < len(sys.argv):
                paths = sys.argv[i + 1]
        run_gaps(scope_arg=scope, paths_arg=paths)

    elif command == "link":
        if len(sys.argv) < 3:
            print("Usage: python vault_intelligence.py link <path/to/note.md>")
            sys.exit(1)
        from vault_ai import run_link
        run_link(sys.argv[2])

    elif command == "promote":
        from vault_ai import run_promote
        run_promote()

    elif command == "inbox":
        from vault_ai import run_inbox_processor
        run_inbox_processor()

    elif command == "connections":
        days = 7
        for i, arg in enumerate(sys.argv[2:], 2):
            if arg == "--days" and i + 1 < len(sys.argv):
                try:
                    days = int(sys.argv[i + 1])
                except ValueError:
                    pass
        from vault_ai import run_connections
        run_connections(days=days)

    elif command == "ask":
        if len(sys.argv) < 3:
            print('Usage: python vault_intelligence.py ask "<your question>"')
            sys.exit(1)
        from vault_ai import run_ask
        run_ask(" ".join(sys.argv[2:]))

    elif command == "write-prep":
        if len(sys.argv) < 3:
            print('Usage: python vault_intelligence.py write-prep "<topic>"')
            sys.exit(1)
        from vault_ai import run_write_prep
        run_write_prep(" ".join(sys.argv[2:]))

    elif command == "contradict":
        from vault_ai import run_contradict
        run_contradict()

    elif command == "synthesize":
        if len(sys.argv) < 3:
            print('Usage: python vault_intelligence.py synthesize "<topic>"')
            sys.exit(1)
        from vault_ai import run_synthesize
        run_synthesize(" ".join(sys.argv[2:]))

    elif command == "skill-capture":
        raw = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        from vault_skills import run_skill_capture
        run_skill_capture(raw)

    elif command == "skill-log":
        if len(sys.argv) < 4:
            print('Usage: python vault_intelligence.py skill-log <slug> "<observation>"')
            sys.exit(1)
        from vault_skills import run_skill_log
        run_skill_log(sys.argv[2], " ".join(sys.argv[3:]))

    elif command == "skill-from-memopipe":
        hours = 24
        if len(sys.argv) > 2:
            try:
                hours = int(sys.argv[2])
            except ValueError:
                pass
        from vault_skills import run_skill_from_memopipe
        run_skill_from_memopipe(hours=hours)

    elif command == "skill-audit":
        if len(sys.argv) < 3:
            print("Usage: python vault_intelligence.py skill-audit <slug>")
            sys.exit(1)
        from vault_skills import run_skill_audit
        run_skill_audit(sys.argv[2])

    elif command == "graph-analyze":
        scope = "vault"
        top_n = 15
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--scope" and i + 1 < len(args):
                scope = args[i + 1]
                i += 2
            elif args[i] == "--top" and i + 1 < len(args):
                try:
                    top_n = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                i += 1
        from vault_graph import run_graph_analyze
        run_graph_analyze(scope=scope, top_n=top_n)

    elif command == "swarm-dashboard":
        from vault_skills import run_swarm_dashboard
        run_swarm_dashboard()

    elif command == "auto-link-orphans":
        scope = "Memory"
        max_links = 3
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--scope" and i + 1 < len(args):
                scope = args[i + 1]
                i += 2
            elif args[i] == "--max" and i + 1 < len(args):
                try:
                    max_links = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                i += 1
        run_auto_link_orphans(scope=scope, max_links=max_links)

    else:
        print(f"Unknown command: {command!r}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
