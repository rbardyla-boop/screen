#!/usr/bin/env python3
"""
vault_brief.py — Memory Core 2.0: the second brain that reaches OUT to you.

The 1.0 system already *detects* everything it needs (the gaps engine writes the
Unfinished Work Dashboard; ``Memory/.loop-state.json`` already tracks how long each
open loop has been hanging). What it never did was *reach the user proactively* —
``memory-check`` is pull-only, so the signal never punched through to behavior.

This module closes that delivery loop. It ranks the live open loops by **staleness**
(time since first seen — a zero-ML "this is about to die" signal), takes the 3
stalest, attaches one concrete next action each, and pushes a tiny **Morning Brief**
as an ambient interrupt (stdout + desktop notification + optional phone push). It
writes a single, overwritten ``Memory/Morning-Brief.md`` (never grows), gates on the
vault guard, and can install a systemd user timer so it fires every morning without
the user remembering anything.

Design decision: see ``docs/PROJECT_CHARTER.md`` (ADR-001) and
``design/MENTAL_MODELS_2.0_ANALYSIS.md``. Deliberately NOT: vector search, RAG,
local-LLM-in-the-loop, knowledge graph, the Rust rewrite. Delivery, not capability.

Usage
-----
  python3 vault_brief.py                 # build + deliver today's brief
  python3 vault_brief.py --no-notify      # print/write only, no notification
  python3 vault_brief.py --skip-guard     # (used internally by memory-check)
  python3 vault_brief.py --install-timer [--hour 7] [--minute 30]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

from dotenv import load_dotenv

# Reuse the canonical detection + age-tracking primitives. Importing here keeps the
# loop fingerprints byte-identical to what the gaps engine wrote into .loop-state.json
# (any drift there would silently corrupt every age we compute).
from vault_intelligence import (  # noqa: E402
    _gap_fingerprint as fingerprint,
    _load_loop_state,
    collect_gaps,
)

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")
GAP_SEPARATOR = " — "  # exactly how vault_intelligence.collect_gaps joins source/text
TOP_N = 3
BRIEF_FILENAME = "Morning-Brief.md"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Loop:
    """One open loop with its staleness, derived from collect_gaps + .loop-state.json."""
    gap: str          # full "[[source]] — text" string (the fingerprinted unit)
    source: str       # "[[path]]" wikilink, or "" if the gap had no separator
    text: str         # human description after the separator
    first_seen: date
    age_days: int


# Leading markdown list/checkbox/number markers the line scanner carries over.
_LEADING_MARKER = re.compile(r"^(?:[-*+]\s+)?(?:\[[ xX]\]\s+)?(?:\d+\.\s+)?")


def _strip_list_marker(text: str) -> str:
    return _LEADING_MARKER.sub("", text, count=1).strip()


def parse_gap(gap: str) -> tuple[str, str]:
    """Split a collect_gaps string into (source_wikilink, clean description)."""
    if GAP_SEPARATOR in gap:
        source, text = gap.split(GAP_SEPARATOR, 1)
        return source.strip(), _strip_list_marker(text.strip())
    return "", _strip_list_marker(gap.strip())


# Scaffolding/echo phrases that collect_gaps matches but are never real loops
# (capture-instruction headers, section labels). The shared gaps engine intentionally
# stays permissive for the dashboard; the brief wants only push-worthy signal, so the
# stricter filter lives here rather than mutating collect_gaps' ownership.
_SCAFFOLDING_PHRASES = (
    "how to capture",
    "current open loops",
    "raw capture",
    "format example",
    "items (newest at top)",
    "throw unfinished",
    "unfinished work dashboard",
    "suggested connections",
)
_MIN_LOOP_TEXT = 8


def is_signal_loop(gap: str) -> bool:
    """True if a gap is a real, push-worthy open loop (not a heading or scaffolding)."""
    _, text = parse_gap(gap)
    text = text.strip()
    if len(text) < _MIN_LOOP_TEXT:
        return False
    if text.startswith("#"):  # markdown heading echoed by the line scanner
        return False
    low = text.lower()
    return not any(phrase in low for phrase in _SCAFFOLDING_PHRASES)


def diversify_by_source(
    loops: Sequence["Loop"], per_source: int = 1, top_n: int = TOP_N
) -> list["Loop"]:
    """Pick the stalest loops while spreading across source notes.

    ``loops`` must already be staleness-sorted. First pass honours ``per_source`` so
    the brief isn't three fragments of one note; a second pass backfills (in staleness
    order) when there aren't enough distinct sources to fill ``top_n``.
    """
    chosen: list[Loop] = []
    counts: dict[str, int] = {}
    for loop in loops:
        if len(chosen) >= top_n:
            break
        if counts.get(loop.source, 0) < per_source:
            chosen.append(loop)
            counts[loop.source] = counts.get(loop.source, 0) + 1
    if len(chosen) < top_n:
        for loop in loops:
            if len(chosen) >= top_n:
                break
            if loop not in chosen:
                chosen.append(loop)
    return chosen[:top_n]


# ---------------------------------------------------------------------------
# Ranking (pure)
# ---------------------------------------------------------------------------

def rank_stale_loops(
    gaps: Sequence[str],
    loop_state: Mapping[str, str],
    today: date,
    top_n: int = TOP_N,
) -> list[Loop]:
    """Return the ``top_n`` stalest loops, oldest first.

    ``loop_state`` maps ``{fingerprint: first_seen_iso}`` (the format
    ``vault_intelligence`` persists). Loops absent from state are treated as first
    seen today (age 0). Ordering is deterministic: by descending age, then by the
    gap string, so ties never depend on input order.
    """
    loops: list[Loop] = []
    for gap in gaps:
        fp = fingerprint(gap)
        first_seen = _parse_iso_date(loop_state.get(fp), default=today)
        age_days = max((today - first_seen).days, 0)
        source, text = parse_gap(gap)
        loops.append(Loop(gap=gap, source=source, text=text,
                          first_seen=first_seen, age_days=age_days))

    loops.sort(key=lambda loop: (-loop.age_days, loop.gap))
    return loops[:top_n]


def _parse_iso_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Next action (pure, deterministic — no model in the critical path)
# ---------------------------------------------------------------------------

_MARKER_PREFIXES = ("[[todo]]", "todo:", "todo", "fixme:", "fixme", "tbd:", "tbd", "wip:", "wip")


def extract_next_action(text: str) -> str:
    """A concrete, honest forcing function for one loop. Never fabricates progress."""
    low = text.lower().strip()

    if "skill debt" in low:
        return "Use it this week or delete the skill."

    cleaned = text.strip()
    stripped_marker = False
    for marker in _MARKER_PREFIXES:
        if low.startswith(marker):
            cleaned = text.strip()[len(marker):].lstrip(" :-").strip()
            stripped_marker = True
            break

    has_cue = any(cue in low for cue in ("need to", "should", "look into", "figure", "finish"))
    if (stripped_marker or has_cue) and cleaned:
        snippet = cleaned if len(cleaned) <= 120 else cleaned[:117] + "..."
        return f"Smallest next step on: {snippet}. Or kill it."

    return "Decide today: advance it or kill it."


# ---------------------------------------------------------------------------
# Rendering (pure)
# ---------------------------------------------------------------------------

def render_brief(loops: Sequence[Loop], today: date) -> str:
    """The full Morning Brief written to Memory/Morning-Brief.md and printed."""
    header = f"# 🧠 Morning Brief — {today.isoformat()}\n"
    if not loops:
        return (
            header
            + "\nNo stale open loops. Inbox zero on unfinished work. 🎉\n"
        )

    lines = [
        header,
        "\nThe things you started and are quietly abandoning — stalest first. "
        "Close one loop today.\n",
    ]
    for i, loop in enumerate(loops, 1):
        source = loop.source or "(unsourced)"
        snippet = loop.text if len(loop.text) <= 160 else loop.text[:157] + "..."
        lines.append(f"\n## {i}. stale {loop.age_days}d · {source}")
        lines.append(snippet)
        lines.append(f"▶ {extract_next_action(loop.text)}")
    lines.append("")
    return "\n".join(lines)


def render_notification(loops: Sequence[Loop]) -> tuple[str, str]:
    """Short (title, body) for desktop / phone delivery."""
    n = len(loops)
    plural = "s" if n != 1 else ""
    title = f"🧠 {n} open loop{plural} going stale"
    if not loops:
        return ("🧠 Memory clear", "No stale open loops today.")
    top = loops[0]
    top_text = top.text if len(top.text) <= 180 else top.text[:177] + "..."
    body = f"Stalest ({top.age_days}d): {top_text}"
    if n > 1:
        body += f"  (+{n - 1} more)"
    return (title[:80], body[:300])


# ---------------------------------------------------------------------------
# Delivery (side effects, dependency-injected for testability)
# ---------------------------------------------------------------------------

def _default_poster(url: str, **kwargs):  # pragma: no cover - thin network wrapper
    import requests
    return requests.post(url, **kwargs)


class Notifier:
    """Routes a notification to whatever ambient channels are enabled.

    Every channel is best-effort and failure-isolated: a missing ``notify-send`` or
    an unreachable ntfy endpoint must never break the brief. Collaborators (``which``,
    ``runner``, ``poster``) are injectable so delivery routing is unit-testable.
    """

    def __init__(
        self,
        desktop: bool = True,
        ntfy_topic: str | None = None,
        ntfy_url: str = "https://ntfy.sh",
        which: Callable[[str], str | None] = shutil.which,
        runner: Callable[..., object] | None = None,
        poster: Callable[..., object] | None = None,
    ) -> None:
        self.desktop = desktop
        self.ntfy_topic = ntfy_topic
        self.ntfy_url = ntfy_url
        self._which = which
        self._runner = runner or subprocess.run
        self._poster = poster or _default_poster

    def notify(self, title: str, body: str) -> None:
        if self.desktop:
            path = self._which("notify-send")
            if path:
                try:
                    self._runner(["notify-send", title, body], timeout=10)
                except Exception:
                    pass
        if self.ntfy_topic:
            url = f"{self.ntfy_url.rstrip('/')}/{self.ntfy_topic}"
            try:
                self._poster(
                    url,
                    data=body.encode("utf-8"),
                    headers={"Title": title},
                    timeout=10,
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# systemd user timer generation (pure render + explicit install)
# ---------------------------------------------------------------------------

def render_systemd_units(exec_command: str, hour: int, minute: int) -> tuple[str, str]:
    """Return (service_unit, timer_unit) text for a daily morning brief."""
    service = (
        "[Unit]\n"
        "Description=Memory Core 2.0 — proactive Morning Brief\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={exec_command}\n"
    )
    timer = (
        "[Unit]\n"
        "Description=Fire the Memory Core Morning Brief every morning\n\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\n"
        "Persistent=true\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    return service, timer


_WRAPPER_TEMPLATE = """#!/bin/bash
# Auto-generated by vault_brief.py --install-timer. Sources env + venv, emits the brief.
set -e
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$SCRIPT_DIR"
if [ -f .env ]; then set -a; source .env; set +a; fi
if [ -d .venv ]; then source .venv/bin/activate; elif [ -d venv ]; then source venv/bin/activate; fi
exec python3 vault_brief.py
"""


def install_timer(hour: int, minute: int) -> None:
    """Write the wrapper script + systemd user units. Does NOT enable (user opts in)."""
    repo_dir = Path(__file__).resolve().parent
    wrapper = repo_dir / "run-morning-brief.sh"
    wrapper.write_text(_WRAPPER_TEMPLATE, encoding="utf-8")
    wrapper.chmod(0o755)

    service, timer = render_systemd_units(
        exec_command=f"/bin/bash {wrapper}", hour=hour, minute=minute
    )
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "vault-morning-brief.service").write_text(service, encoding="utf-8")
    (unit_dir / "vault-morning-brief.timer").write_text(timer, encoding="utf-8")

    print("Wrote:")
    print(f"  {wrapper}")
    print(f"  {unit_dir / 'vault-morning-brief.service'}")
    print(f"  {unit_dir / 'vault-morning-brief.timer'}")
    print(f"\nMorning Brief will fire daily at {hour:02d}:{minute:02d}. Enable it with:\n")
    print("  systemctl --user daemon-reload \\")
    print("    && systemctl --user enable --now vault-morning-brief.timer")
    print("\n(One-time, on most desktops: `loginctl enable-linger $USER` so it runs when logged out.)")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_and_deliver(scope: str, notify: bool) -> int:
    vault = Path(VAULT_PATH)
    gaps = collect_gaps([scope])
    signal = [g for g in gaps if is_signal_loop(g)]
    state = _load_loop_state()
    today = date.today()
    ranked = rank_stale_loops(signal, state, today, top_n=max(len(signal), 1))
    top = diversify_by_source(ranked, per_source=1, top_n=TOP_N)

    brief = render_brief(top, today)
    out = vault / "Memory" / BRIEF_FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(brief, encoding="utf-8")  # single file, overwritten daily (anti-bloat)

    print(brief)
    print(f"(written: {out})")

    if notify and top:
        title, body = render_notification(top)
        Notifier(
            desktop=True,
            ntfy_topic=os.environ.get("NTFY_TOPIC") or None,
            ntfy_url=os.environ.get("NTFY_URL", "https://ntfy.sh"),
        ).notify(title, body)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Core 2.0 — proactive Morning Brief")
    parser.add_argument("--scope", default="Memory", help="vault scope to scan (default: Memory)")
    parser.add_argument("--no-notify", action="store_true", help="print/write only; no notification")
    parser.add_argument("--skip-guard", action="store_true", help="skip the guard (used by memory-check)")
    parser.add_argument("--install-timer", action="store_true", help="install a systemd user timer and exit")
    parser.add_argument("--hour", type=int, default=7, help="timer hour (default 7)")
    parser.add_argument("--minute", type=int, default=30, help="timer minute (default 30)")
    args = parser.parse_args()

    if args.install_timer:
        install_timer(args.hour, args.minute)
        return

    if not VAULT_PATH:
        print("Error: VAULT_PATH not set in .env")
        sys.exit(1)

    if not args.skip_guard:
        try:
            from vault_guard import run_audit
            code = run_audit(strict=False)
            if code >= 2:
                print("\n[GUARD] CRITICAL: vault health check failed. Fix violations before the brief.")
                sys.exit(2)
        except SystemExit:
            raise
        except Exception:
            print("[GUARD] Could not load vault_guard (proceeding anyway)")

    sys.exit(build_and_deliver(scope=args.scope, notify=not args.no_notify))


if __name__ == "__main__":
    main()
