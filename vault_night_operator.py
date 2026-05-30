#!/usr/bin/env python3
"""
Vault Night Operator — reads active project repos, compares to vault notes,
and writes a nightly Markdown report into the Obsidian vault.

Usage:
    python vault_night_operator.py \
        --vault "/home/user/Obsidian Vault" \
        --repos "/path/to/repo1,/path/to/repo2"

    python vault_night_operator.py \
        --vault "/home/user/Obsidian Vault" \
        --repos "/path/to/repo" \
        --dry-run

Allowed:  read files, read git status, write Markdown into vault
Forbidden: edit source code, commit changes, call live agents, modify policy files
"""

import argparse
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────


def run_git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def extract_section(text: str, heading: str) -> str:
    h = re.escape(heading)
    pattern = r"#{1,6} " + h + r"\s*\n(.*?)(?=\n#{1,6} |\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return ""
    body = m.group(1).strip()
    body = re.sub(r"\n+---+\s*$", "", body).strip()
    return body


# ── repo state ────────────────────────────────────────────────────────────────


def check_repo(repo_path: Path) -> dict:
    """Gather read-only git and file state for a repo."""
    name = repo_path.name
    branch = run_git(repo_path, "branch", "--show-current") or "unknown"
    last_commit = run_git(repo_path, "log", "-1", "--format=%h %s") or "no commits"
    last_commit_ago = run_git(repo_path, "log", "-1", "--format=%ar") or "unknown"
    recent_commits = run_git(repo_path, "log", "--since=7 days ago", "--oneline")
    is_stale = len(recent_commits.splitlines()) == 0
    working_tree_clean = run_git(repo_path, "status", "--porcelain") == ""
    brief_path = repo_path / "docs" / "LLM_CONTEXT_BRIEF.md"
    has_brief = brief_path.exists()
    brief_snippet = ""
    if has_brief:
        brief_text = read_file(brief_path)
        # Extract next step line from brief
        m = re.search(r"\*\*Feature \d[^*]*\*\*.*", brief_text)
        brief_snippet = m.group(0)[:80] if m else brief_text[:80]

    return {
        "name": name,
        "path": str(repo_path),
        "branch": branch,
        "last_commit": last_commit,
        "last_commit_ago": last_commit_ago,
        "is_stale": is_stale,
        "working_tree_clean": working_tree_clean,
        "has_brief": has_brief,
        "brief_snippet": brief_snippet,
    }


# ── vault note parsing ────────────────────────────────────────────────────────


def slug(name: str) -> str:
    """Convert repo directory name to a candidate project note filename."""
    return name.lower().replace("_", "-")


def read_project_note(projects_dir: Path, repo_name: str) -> dict | None:
    """Try several name variants to find the project note."""
    candidates = [
        projects_dir / f"{repo_name}.md",
        projects_dir / f"{slug(repo_name)}.md",
    ]
    for path in candidates:
        text = read_file(path)
        if text:
            return {
                "found": True,
                "path": str(path),
                "status": extract_section(text, "Status") or "unknown",
                "next_move": extract_section(text, "Next Move"),
                "current_goal": extract_section(text, "Current Goal"),
                "session_log": extract_section(text, "Session Log"),
            }
    return {"found": False, "path": None, "status": "no note", "next_move": "", "current_goal": "", "session_log": ""}


def detect_note_staleness(note: dict) -> bool:
    """True if the session log has no entry in the last 7 days."""
    log = note.get("session_log", "")
    if not log:
        return True
    today = date.today()
    for line in log.splitlines():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if m:
            try:
                entry_date = date.fromisoformat(m.group(1))
                if (today - entry_date).days <= 7:
                    return False
            except ValueError:
                pass
    return True


# ── report generation ─────────────────────────────────────────────────────────


def generate_report(
    today: str,
    repo_states: list[dict],
    notes: dict[str, dict],
) -> str:
    active_rows = []
    missing_action = []
    stale_projects = []
    warnings = []
    morning_start = None

    for rs in repo_states:
        name = rs["name"]
        note = notes.get(name, {})
        status = note.get("status", "no note")
        next_move = note.get("next_move", "").splitlines()[0][:60] if note.get("next_move") else "—"
        risk = "⚠ dirty" if not rs["working_tree_clean"] else ("⚠ stale" if rs["is_stale"] else "ok")

        active_rows.append(f"| {name} | {status} | {rs['branch'][:30]} | {next_move} | {risk} |")

        if not note.get("next_move"):
            missing_action.append(f"- **{name}** — no `## Next Move` in project note")

        if rs["is_stale"] or detect_note_staleness(note):
            stale_projects.append(f"- **{name}** — last commit {rs['last_commit_ago']}")

        if not rs["has_brief"]:
            warnings.append(f"- **{name}** — no `docs/LLM_CONTEXT_BRIEF.md` (run `python scripts/project_snapshot.py --write`)")

        if not note.get("found"):
            warnings.append(f"- **{name}** — no vault project note in `02 - Projects/`")

        if morning_start is None and status.lower() not in ("frozen", "archived", "no note"):
            morning_start = (name, next_move)

    # Active projects table
    table_rows = "\n".join(active_rows) if active_rows else "_(none)_"
    table = (
        "| Project | Status | Branch | Next Move | Risk |\n"
        "|---|---|---|---|---|\n"
        f"{table_rows}"
    )

    # Missing action section
    missing_str = "\n".join(missing_action) if missing_action else "_(none)_"

    # Stale section
    stale_str = "\n".join(stale_projects) if stale_projects else "_(none)_"

    # Morning start
    if morning_start:
        project, move = morning_start
        morning = (
            f"1. Open project: **{project}**\n"
            f"2. Read: `docs/LLM_CONTEXT_BRIEF.md`\n"
            f"3. Do: {move}"
        )
    else:
        morning = "_(no active projects)_"

    # Warnings
    warnings_str = "\n".join(warnings) if warnings else "_(none)_"

    return f"""# Nightly Vault Report — {today}

## Active Projects
{table}

## Projects Missing a Next Action
{missing_str}

## Stale Projects (no commit or log update in 7+ days)
{stale_str}

## Suggested Morning Start
{morning}

## Warnings
{warnings_str}

---
_Generated by vault_night_operator.py — read-only scan, no source edits made._
"""


def update_project_index(vault_path: Path, repo_states: list[dict], notes: dict[str, dict]) -> str:
    rows = []
    repo_rows = []
    for rs in repo_states:
        name = rs["name"]
        note = notes.get(name, {})
        status = note.get("status", "no note")
        branch = rs["branch"][:35]
        next_move = note.get("next_move", "").splitlines()[0][:50] if note.get("next_move") else "—"
        rows.append(f"| {name} | {status} | {branch} | {next_move} |")
        repo_rows.append(f"| {name} | {rs['path']} |")

    today = date.today().isoformat()
    table = "\n".join(rows)
    repo_table = "\n".join(repo_rows)

    return f"""# Project Index
_Last updated {today} by vault_night_operator.py_

| Project | Status | Branch | Next Move |
|---|---|---|---|
{table}

## Repo Paths
| Project | Path |
|---|---|
{repo_table}

## Notes
- Projects without `## Next Move` in their note are flagged as missing action.
- Projects with no session log update or commit in 7+ days are flagged as stale.
- For each project, `docs/LLM_CONTEXT_BRIEF.md` is the machine-readable brief for Claude Code cold-starts.
"""


def update_active_context(vault_path: Path, repo_states: list[dict], notes: dict[str, dict]) -> str:
    today = date.today().isoformat()
    lines = [f"# Active Context\n_Updated {today}_\n"]
    for rs in repo_states:
        name = rs["name"]
        note = notes.get(name, {})
        if note.get("status", "").lower() in ("frozen", "archived"):
            continue
        goal = note.get("current_goal", "")
        next_move = note.get("next_move", "")
        lines.append(f"## {name}")
        lines.append(f"Branch: `{rs['branch']}`  |  Last commit: {rs['last_commit_ago']}")
        if goal:
            lines.append(f"Goal: {goal}")
        if next_move:
            first_line = next_move.splitlines()[0]
            lines.append(f"Next: {first_line}")
        lines.append("")
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault Night Operator")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault root")
    parser.add_argument("--repos", required=True, help="Comma-separated repo paths")
    parser.add_argument("--dry-run", action="store_true", help="Print report without writing")
    args = parser.parse_args()

    vault = Path(args.vault)
    repo_paths = [Path(p.strip()) for p in args.repos.split(",") if p.strip()]
    today = date.today().isoformat()

    # Validate
    for rp in repo_paths:
        if not rp.exists():
            print(f"WARNING: repo path does not exist: {rp}", file=sys.stderr)

    projects_dir = vault / "02 - Projects"
    memory_dir = vault / "05 - Memory Layer"
    reports_dir = vault / "06 - Automation" / "Nightly Reports"

    # Gather state
    repo_states = [check_repo(rp) for rp in repo_paths if rp.exists()]
    notes = {rs["name"]: read_project_note(projects_dir, rs["name"]) for rs in repo_states}

    # Generate outputs
    report = generate_report(today, repo_states, notes)
    index = update_project_index(vault, repo_states, notes)
    context = update_active_context(vault, repo_states, notes)

    if args.dry_run:
        print("=== NIGHTLY REPORT (dry run) ===")
        print(report)
        print("=== PROJECT INDEX ===")
        print(index)
        print("=== ACTIVE CONTEXT ===")
        print(context)
        return

    # Write
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{today}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Written: {report_path}", file=sys.stderr)

    memory_dir.mkdir(parents=True, exist_ok=True)
    index_path = memory_dir / "Project Index.md"
    index_path.write_text(index, encoding="utf-8")
    print(f"Updated: {index_path}", file=sys.stderr)

    context_path = memory_dir / "Active Context.md"
    context_path.write_text(context, encoding="utf-8")
    print(f"Updated: {context_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
