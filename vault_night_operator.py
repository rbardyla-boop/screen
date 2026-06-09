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

Allowed:  read files, read git status, write Markdown into vault, and tidy the
          Clippings/ drop zone (regenerate _Index.md, quarantine duplicate clips)
Forbidden: edit source code, commit changes, call live agents, modify policy files
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
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


# ── morning briefing ──────────────────────────────────────────────────────────


def extract_recent_connections(vault_path: Path) -> str:
    """Extract recent note connections from the latest graph report or synthesis."""
    graph_dir = vault_path / "Memory" / "Outputs"
    if not graph_dir.exists():
        return "_(vault graph not yet generated)_"

    # Find latest graph or synthesis report
    files = sorted(graph_dir.glob("*synthesis*.md"), reverse=True)
    if not files:
        return "_(no recent synthesis found)_"

    latest = files[0]
    text = read_file(latest)

    # Extract section mentioning connections or links
    connections_section = extract_section(text, "Connections") or extract_section(text, "Evidence")
    if not connections_section:
        # Fallback: pull first few bullet points
        lines = text.split("\n")
        bullets = [l for l in lines if l.strip().startswith("- ") or l.strip().startswith("* ")][:3]
        if bullets:
            return "\n".join(bullets[:3])
        return "_(synthesis generated but no clear connections yet)_"

    # Return first 3 lines of the section
    lines = connections_section.split("\n")
    return "\n".join(lines[:3]) if lines else "_(no connections)_"


def infer_active_pattern(repo_states: list[dict], notes: dict[str, dict]) -> str:
    """Infer the current pattern of work from active projects."""
    active = [rs for rs in repo_states if rs.get("has_brief")]
    if not active:
        return "_(no active projects with briefs)_"

    # Get status of active projects
    statuses = []
    for rs in active[:2]:  # Top 2
        name = rs["name"]
        note = notes.get(name, {})
        status = note.get("status", "in progress")
        statuses.append(f"- **{name}**: {status}")

    return "\n".join(statuses) if statuses else "_(observing)_"


def get_reflection_prompt() -> str:
    """Return one of the three open questions from CLAUDE.md."""
    prompts = [
        "**Institutional Vulnerability**: How does your vault defend against seizure or loss? Design a minimal resilient substrate.",
        "**Meta-Governance**: When does rule-hardening become too rigid? What signal indicates RULES_RUTHLESS needs revision?",
        "**Skill Pipeline**: Does the pipeline discover latent skills or create new ones through decomposition? Run a controlled test.",
    ]
    # Rotate based on day of week
    import hashlib
    today_hash = hashlib.md5(date.today().isoformat().encode()).digest()[0]
    return prompts[today_hash % len(prompts)]


def generate_morning_briefing(
    vault_path: Path,
    repo_states: list[dict],
    notes: dict[str, dict],
) -> str:
    """Generate a lightweight morning briefing (3 sections: connections, pattern, reflection)."""
    today = date.today().isoformat()
    connections = extract_recent_connections(vault_path)
    pattern = infer_active_pattern(repo_states, notes)
    reflection = get_reflection_prompt()

    return f"""# Morning Briefing — {today}

## Connections
{connections}

## Pattern
{pattern}

## Reflection Prompt
{reflection}

---
_Generated by vault_night_operator.py — 6am briefing_
"""


# ── clippings organizer ───────────────────────────────────────────────────────

CLIPPINGS_DIRNAME = "Clippings"
CLIP_INDEX_NAME = "_Index.md"
CLIP_DUP_DIRNAME = "_Duplicates"
_WIKILINK_UNSAFE = set("[]#|^")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Best-effort parse of a note's flat scalar YAML frontmatter fields.

    Only top-level `key: value` lines are captured; nested list items (indented
    `- item` lines, e.g. author/tags) are intentionally ignored.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fields: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        fields.setdefault(key, val)  # first occurrence wins
    return fields


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1).replace("www.", "") if m else url


def _base_title(stem: str) -> str:
    """Drop a trailing ' <n>' Web-Clipper reclip suffix; lowercase for matching.

    "Agentic OS Build 2" -> "agentic os build". Used so that only true re-clips
    of one page (same source AND same base title) are treated as duplicates —
    two different tweets that share a generic source like x.com/home are not.
    """
    base = re.sub(r"\s+\d+$", "", stem).strip()
    return (base or stem).lower()


def _read_clip(path: Path) -> dict:
    fm = parse_frontmatter(read_file(path))
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": path,
        "title": fm.get("title") or path.stem,
        "source": (fm.get("source") or "").strip().rstrip("/"),
        "created": (fm.get("created") or "").strip(),
        "size": size,
    }


def _clip_link(clip: dict) -> str:
    """Wikilink when the filename is wikilink-safe, else a same-folder md link."""
    stem = clip["path"].stem
    if _WIKILINK_UNSAFE.isdisjoint(stem):
        link = f"[[{stem}]]"
    else:
        link = f"[{clip['title']}](<{clip['path'].name}>)"
    src = clip["source"]
    return f"- {link} · [{_domain(src)}]({src})" if src else f"- {link}"


def _build_clip_index(canonical: list[dict], quarantined: list[dict]) -> str:
    months: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    undated: list[dict] = []
    for c in canonical:
        m = re.match(r"(\d{4}-\d{2})-\d{2}", c["created"])
        (months[m.group(1)][c["created"]].append(c) if m else undated.append(c))

    lines = [
        "---",
        "tags: [clippings-index, moc]",
        "---",
        f"# 📎 Clippings — {len(canonical)} notes",
        f"_Auto-generated by vault_night_operator.py · {date.today().isoformat()}_",
        "",
        "> Drop new clips into `Clippings/`. This index and the duplicate"
        " quarantine refresh every night — do not edit by hand.",
        "",
    ]
    for month in sorted(months, reverse=True):
        count = sum(len(d) for d in months[month].values())
        lines.append(f"## {month}  ({count})")
        for day in sorted(months[month], reverse=True):
            lines.append(f"### {day}")
            for c in sorted(months[month][day], key=lambda x: x["title"].lower()):
                lines.append(_clip_link(c))
        lines.append("")
    if undated:
        lines.append(f"## Undated  ({len(undated)})")
        for c in sorted(undated, key=lambda x: x["title"].lower()):
            lines.append(_clip_link(c))
        lines.append("")
    if quarantined:
        lines.append(f"## ⚠ Quarantined duplicates ({len(quarantined)})")
        lines.append(
            f"_In `{CLIPPINGS_DIRNAME}/{CLIP_DUP_DIRNAME}/` — same source URL as a kept"
            " clip. Review and delete when ready._"
        )
        for c in sorted(quarantined, key=lambda x: x["title"].lower()):
            src = c["source"]
            lines.append(f"- {c['title']}" + (f" · {_domain(src)}" if src else ""))
        lines.append("")
    return "\n".join(lines)


def organize_clippings(vault: Path, dry_run: bool = False) -> dict:
    """Index web clippings and quarantine exact same-source duplicates.

    Non-destructive apart from moving duplicate clips (same ``source:`` URL as a
    kept clip) into ``Clippings/_Duplicates/`` for review. The most complete copy
    (largest file, then earliest created) stays in place. Regenerates
    ``Clippings/_Index.md``. Operates ONLY on top-level ``*.md`` inside
    ``Clippings/`` — subfolders the user made are left untouched.
    """
    clip_dir = vault / CLIPPINGS_DIRNAME
    if not clip_dir.is_dir():
        return {"present": False}
    dup_dir = clip_dir / CLIP_DUP_DIRNAME
    index_path = clip_dir / CLIP_INDEX_NAME

    clips = [
        _read_clip(p)
        for p in sorted(clip_dir.glob("*.md"))
        if p.name != CLIP_INDEX_NAME
    ]

    # A duplicate = same source URL AND same base title (so re-clips "X" / "X 1"
    # collapse, but two distinct pages sharing a generic source — e.g. x.com/home
    # — are kept apart). Prefer false negatives over wrongly quarantining a clip.
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for c in clips:
        if c["source"]:
            by_key[(c["source"].lower(), _base_title(c["path"].stem))].append(c)

    to_quarantine: list[dict] = []
    for group in by_key.values():
        if len(group) < 2:
            continue
        # keep the most complete copy (largest, then earliest created, then name)
        group.sort(key=lambda c: (-c["size"], c["created"] or "9999", c["path"].name.lower()))
        to_quarantine.extend(group[1:])

    moved = 0
    if to_quarantine and not dry_run:
        dup_dir.mkdir(exist_ok=True)
    for dup in to_quarantine:
        dest = dup_dir / dup["path"].name
        n = 1
        while dest.exists():
            dest = dup_dir / f"{dup['path'].stem} (dup {n}){dup['path'].suffix}"
            n += 1
        if not dry_run:
            dup["path"].rename(dest)
        moved += 1

    quarantined_paths = {d["path"] for d in to_quarantine}
    canonical = [c for c in clips if c["path"] not in quarantined_paths]

    # the quarantine section reflects everything currently in _Duplicates/ so it
    # persists across nights until the user clears it
    existing_dups: list[dict] = []
    if dup_dir.is_dir():
        existing_dups = [_read_clip(p) for p in sorted(dup_dir.glob("*.md"))]
    if dry_run:  # nothing was moved, so fold the would-be moves into the preview
        existing_dups = existing_dups + to_quarantine

    index_md = _build_clip_index(canonical, existing_dups)
    if not dry_run:
        index_path.write_text(index_md, encoding="utf-8")

    return {
        "present": True,
        "total": len(clips),
        "unique": len(canonical),
        "duplicates_moved": moved,
        "duplicates_total": len(existing_dups),
        "index_path": index_path,
        "dry_run": dry_run,
    }


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault Night Operator")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault root")
    parser.add_argument("--repos", required=True, help="Comma-separated repo paths")
    parser.add_argument("--dry-run", action="store_true", help="Print report without writing")
    parser.add_argument("--briefing", action="store_true", help="Generate 6am morning briefing instead of nightly report")
    parser.add_argument("--no-clippings", action="store_true", help="Skip Clippings indexing/dedupe in nightly mode")
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
    briefing_dir = vault / "06 - Automation" / "Morning Briefings"

    # Gather state
    repo_states = [check_repo(rp) for rp in repo_paths if rp.exists()]
    notes = {rs["name"]: read_project_note(projects_dir, rs["name"]) for rs in repo_states}

    # Morning briefing mode
    if args.briefing:
        briefing = generate_morning_briefing(vault, repo_states, notes)
        if args.dry_run:
            print("=== MORNING BRIEFING (dry run) ===")
            print(briefing)
            return
        briefing_dir.mkdir(parents=True, exist_ok=True)
        briefing_path = briefing_dir / f"{today}.md"
        briefing_path.write_text(briefing, encoding="utf-8")
        print(f"Written: {briefing_path}", file=sys.stderr)
        return

    # Nightly report mode (default)
    report = generate_report(today, repo_states, notes)
    index = update_project_index(vault, repo_states, notes)
    context = update_active_context(vault, repo_states, notes)

    clip = None
    if not args.no_clippings:
        clip = organize_clippings(vault, dry_run=args.dry_run)

    if args.dry_run:
        print("=== NIGHTLY REPORT (dry run) ===")
        print(report)
        print("=== PROJECT INDEX ===")
        print(index)
        print("=== ACTIVE CONTEXT ===")
        print(context)
        if clip and clip.get("present"):
            print("=== CLIPPINGS (dry run) ===")
            print(
                f"  {clip['total']} clips · {clip['unique']} unique · "
                f"{clip['duplicates_moved']} would be quarantined"
            )
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

    if clip and clip.get("present"):
        print(
            f"Clippings: indexed {clip['unique']} unique, quarantined "
            f"{clip['duplicates_moved']} duplicate(s) → {clip['index_path']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
