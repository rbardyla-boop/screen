#!/usr/bin/env python3
"""
daily-memory-synthesis.py

Pulls a day's screen + audio from Screenpipe, reads your open loops,
and produces an End-of-Day Memory Report.

Usage:
  python daily-memory-synthesis.py              # today
  python daily-memory-synthesis.py --date 2026-05-28  # backfill any past date
"""

import datetime
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from ai_provider import ask_ai

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")
SCREENPIPE_URL: str = os.environ.get("SCREENPIPE_URL", "http://localhost:3030/search")
SCREENPIPE_API_KEY: str = os.environ.get("SCREENPIPE_API_KEY", "")


def _utc_day_window(date: datetime.date) -> tuple[str, str]:
    """Return (start, end) UTC ISO strings covering the full local calendar day."""
    local_tz = datetime.datetime.now().astimezone().tzinfo
    start = datetime.datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=local_tz)
    end = datetime.datetime(date.year, date.month, date.day, 23, 59, 59, tzinfo=local_tz)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (
        start.astimezone(datetime.timezone.utc).strftime(fmt),
        end.astimezone(datetime.timezone.utc).strftime(fmt),
    )


def get_raw_for_date(date: datetime.date) -> str:
    """Fetch all OCR/transcription from Screenpipe for the given calendar day."""
    start, end = _utc_day_window(date)
    headers = {"Authorization": f"Bearer {SCREENPIPE_API_KEY}"} if SCREENPIPE_API_KEY else {}
    try:
        resp = requests.get(
            SCREENPIPE_URL,
            params={"content_type": "all", "start_time": start, "end_time": end, "limit": 2000},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        segments = []
        for item in resp.json().get("data", []):
            content = item.get("content", {})
            text = content.get("text") or content.get("transcription")
            if text:
                segments.append(text.strip())
        return "\n".join(segments)
    except Exception as e:
        print(f"[synthesis] Error pulling from Screenpipe: {e}")
        return ""


def read_file_safe(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def get_current_open_loops(vault: Path) -> str:
    open_loops = read_file_safe(vault / "Memory" / "Open-Loops.md")
    dashboard = read_file_safe(vault / "Memory" / "Unfinished Work Dashboard.md")
    return (
        f"=== CURRENT OPEN LOOPS (raw capture) ===\n{open_loops}\n\n"
        f"=== CURRENT UNFINISHED WORK DASHBOARD ===\n{dashboard}"
    )


def synthesize_daily_memory(raw: str, open_loops_context: str, date: str) -> str:
    if not raw.strip():
        return f"No screen/audio data found for {date}. Screenpipe may not have been running."

    prompt = f"""You are an extremely effective, no-bullshit personal memory prosthetic for someone who starts ambitious things and then completely loses track of them.

Your job is to produce the **End of Day Memory Report** for {date}.

You are given two things:

1. RAW SCREEN + AUDIO from that day (OCR + any voice transcripts). This is what the person actually did, looked at, and said out loud.
2. The person's CURRENT open loops / unfinished work (from their second brain).

Do the following with brutal clarity:

- Extract any NEW clear intentions, half-started projects, or "I should..." moments from the activity.
- For EVERY existing open loop in the context, honestly answer:
  - Did the day's activity provide any useful new information, link, idea, or next step for this item?
  - If yes → suggest a concrete, actionable path forward (specific next action the person can take).
  - If no → clearly state "No new useful context today. Still blocked on: [one sentence summary of the blocker]". Do not invent progress.
- Prioritize signal. Ignore noise, routine browsing, and completed busywork.
- The output must help the person remember what actually matters and what to do about it.

Output format (use exactly these markdown headings):

# End of Day Memory Report — {date}

## What Actually Happened (relevant to your memory)
(Short, honest, 4-8 bullets max. Only things that matter for unfinished work.)

## New Open Loops Captured
- Bullet list of genuinely new unfinished items spotted. If none, say "None detected."

## Status of Existing Open Loops + Suggested Paths
For each important open loop from the context:
- **[[Link or name of the loop]]**
  - Relevant activity: ...
  - Status: (New path available / Still blocked / Partial progress)
  - Suggested next action: ...

## Persistent WIP (no helpful new context yet)
List the open loops still hanging with no useful movement. These stay alive until future days provide a link.

## One Thing Worth Paying Attention To
The single highest-leverage thing for your long-term memory and unfinished work.

Be cold, precise, and maximally useful. Do not flatter or add fluff.

=== RAW SCREEN/AUDIO DATA ===
{raw[:18000]}

=== PERSON'S CURRENT OPEN LOOPS & DASHBOARD ===
{open_loops_context[:8000]}
"""

    return ask_ai(prompt, tier="heavy")


def write_report(vault: Path, date: str, content: str) -> Path:
    folder = vault / "Memory" / "Daily Reviews"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{date}.md"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    if not VAULT_PATH:
        print("Error: VAULT_PATH not set in .env")
        sys.exit(1)

    # Parse optional --date YYYY-MM-DD
    target_date = datetime.date.today()
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 >= len(sys.argv):
            print("Error: --date requires a value (YYYY-MM-DD)")
            sys.exit(1)
        try:
            target_date = datetime.date.fromisoformat(sys.argv[idx + 1])
        except ValueError:
            print(f"Error: invalid date '{sys.argv[idx + 1]}' — use YYYY-MM-DD")
            sys.exit(1)

    date_str = target_date.isoformat()
    vault = Path(VAULT_PATH)

    print("=== Daily Memory Synthesis ===")
    print(f"Date: {date_str}")
    print("Pulling screen + audio from Screenpipe...")

    raw = get_raw_for_date(target_date)
    if not raw:
        print(f"No data from Screenpipe for {date_str}. Nothing to synthesize.")
        return

    print(f"Got {len(raw)} characters. Loading your current open loops...")
    context = get_current_open_loops(vault)

    print("Running synthesis...")
    report = synthesize_daily_memory(raw, context, date_str)

    report_path = write_report(vault, date_str, report)
    print(f"\n✓ Report written to:\n  {report_path}")


if __name__ == "__main__":
    main()
