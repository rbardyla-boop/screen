"""
vault_skills.py — Skill bank management (MUSE lifecycle + Swarm Colony dashboard).

Commands exposed via vault_intelligence.py:
  skill-capture, skill-log, skill-from-memopipe, skill-audit, swarm-dashboard
"""

import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from ai_provider import ask_ai

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")
MEMOPIPE_DB: str = os.environ.get(
    "MEMOPIPE_DB",
    os.path.expanduser("~/.local/share/memopipe/captures.db"),
)

_NEVER_SCAN: list[str] = [
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

_WIKILINK_RE = re.compile(r'\[\[([^\]|\n#]+?)(?:\|[^\]]*)?(?:#[^\]]*)?\]\]')

SKILL_MD_TEMPLATE = """\
---
type: skill
created: {date}
last_used: {date}
use_count: 0
revalidate_after: "{revalidate}"
status: active
---

# {title}

## When to Use
{when_to_use}

## Steps
{steps}

## Pitfalls
{pitfalls}

## Test Scenarios
- [ ]
- [ ]

## Related Skills

"""


def _should_skip_path(p: Path, vault: Path) -> bool:
    try:
        rel = str(p.relative_to(vault)).lower()
    except ValueError:
        rel = str(p).lower()
    return any(bad.lower() in rel for bad in _NEVER_SCAN)


def _make_slug(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"\s+", "-", slug)[:max_len]


def _parse_skill_ai_output(raw: str) -> dict[str, str]:
    KEYS = ["SKILL_NAME", "TITLE", "WHEN_TO_USE", "STEPS", "PITFALLS", "REVALIDATE_AFTER"]
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        matched = False
        for key in KEYS:
            if line.startswith(f"{key}:"):
                if current_key:
                    result[current_key] = "\n".join(current_lines).strip()
                current_key = key
                after_colon = line[len(key) + 1:].strip()
                current_lines = [after_colon] if after_colon else []
                matched = True
                break
        if not matched and current_key:
            current_lines.append(line)

    if current_key:
        result[current_key] = "\n".join(current_lines).strip()

    return result


def run_skill_capture(raw_text: str | None = None) -> None:
    """Convert raw text (screen capture excerpt, idea, paste) into a SKILL.md."""
    vault = Path(VAULT_PATH)

    if raw_text is None:
        print("Paste raw text to convert to a skill (Ctrl+D when done):")
        try:
            raw_text = sys.stdin.read().strip()
        except EOFError:
            raw_text = ""

    if not raw_text:
        print("No input.")
        return

    result = ask_ai(
        "Extract a reusable skill from this raw capture.\n"
        "A skill is a repeatable thinking tool or workflow — NOT a one-off task.\n"
        "If the text doesn't describe something repeatable, output SKILL_NAME: SKIP.\n\n"
        f"RAW TEXT:\n{raw_text[:3000]}\n\n"
        "Output exactly these keys (STEPS and PITFALLS may have multiple bullet lines after the key):\n"
        "SKILL_NAME: <kebab-case-name>\n"
        "TITLE: <Human Readable Title>\n"
        "WHEN_TO_USE: <one sentence trigger>\n"
        "STEPS:\n- step one\n- step two\n"
        "PITFALLS:\n- pitfall one\n"
        "REVALIDATE_AFTER: 10 uses or 30 days"
    )

    parsed = _parse_skill_ai_output(result)
    skill_name = parsed.get("SKILL_NAME", "SKIP").strip()

    if skill_name.upper() == "SKIP" or not skill_name:
        print("AI says this isn't a reusable skill.")
        print("Add to Open-Loops.md instead? (y/n): ", end="", flush=True)
        try:
            if input().strip().lower() == "y":
                loops = vault / "Memory" / "Open-Loops.md"
                loops.parent.mkdir(parents=True, exist_ok=True)
                with loops.open("a", encoding="utf-8") as f:
                    f.write(f"\n- {raw_text[:200]}\n")
                print("Added to Open-Loops.md.")
        except (ValueError, EOFError):
            pass
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = _make_slug(skill_name.lower())
    skill_dir = vault / "Memory" / "Skills" / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    content = SKILL_MD_TEMPLATE.format(
        date=date_str,
        title=parsed.get("TITLE", skill_name),
        when_to_use=parsed.get("WHEN_TO_USE", "TODO: fill in"),
        steps=parsed.get("STEPS", "- TODO"),
        pitfalls=parsed.get("PITFALLS", "- TODO"),
        revalidate=parsed.get("REVALIDATE_AFTER", "10 uses or 30 days"),
    )

    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")

    memory_path = skill_dir / ".memory.md"
    memory_path.write_text(
        f"# Memory: {parsed.get('TITLE', skill_name)}\n\n"
        f"## Observations\n\n"
        f"- {date_str}: Created from raw capture\n",
        encoding="utf-8",
    )

    print(f"\nSkill created: Memory/Skills/{slug}/SKILL.md")
    print("Open in Obsidian and refine the test scenarios.")
    print(f"Record observations with: skill-log {slug} \"<what happened>\"")


def run_skill_log(skill_slug: str, observation: str) -> None:
    """Append an observation to a skill's .memory.md and update last_used + use_count."""
    vault = Path(VAULT_PATH)
    skills_dir = vault / "Memory" / "Skills"

    skill_dir = skills_dir / skill_slug
    if not skill_dir.exists():
        candidates = (
            [d for d in skills_dir.iterdir() if d.is_dir() and skill_slug.lower() in d.name.lower()]
            if skills_dir.exists()
            else []
        )
        if len(candidates) == 1:
            skill_dir = candidates[0]
        elif len(candidates) > 1:
            print(f"Multiple matches: {[d.name for d in candidates]}")
            print("Be more specific.")
            return
        else:
            print(f"Skill not found: {skill_slug!r}")
            print(f"Skills dir: {skills_dir}")
            return

    date_str = datetime.now().strftime("%Y-%m-%d")
    memory_path = skill_dir / ".memory.md"

    if not memory_path.exists():
        memory_path.write_text(
            f"# Memory: {skill_dir.name}\n\n## Observations\n\n",
            encoding="utf-8",
        )

    with memory_path.open("a", encoding="utf-8") as f:
        f.write(f"- {date_str}: {observation}\n")

    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        text = skill_path.read_text(encoding="utf-8")
        text = re.sub(r"last_used: \d{4}-\d{2}-\d{2}", f"last_used: {date_str}", text)

        def _inc(m: re.Match) -> str:
            return f"use_count: {int(m.group(1)) + 1}"

        text = re.sub(r"use_count: (\d+)", _inc, text)
        skill_path.write_text(text, encoding="utf-8")

    print(f"Logged to {skill_dir.name}/.memory.md")


def run_skill_from_memopipe(hours: int = 24) -> None:
    """Query MemoPipe's local SQLite for recent captures and detect skill candidates."""
    db_path = Path(MEMOPIPE_DB)
    if not db_path.exists():
        print(f"[skill-from-memopipe] MemoPipe DB not found: {db_path}")
        print("Is memopipe running? Check MEMOPIPE_DB in .env")
        return

    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ts, type, content FROM captures WHERE ts >= ? ORDER BY ts",
            (cutoff,),
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[skill-from-memopipe] DB error: {e}")
        return

    if not rows:
        print(f"No captures in the last {hours} hours.")
        return

    segments = [r["content"].strip() for r in rows if r["content"].strip()]
    raw = "\n".join(segments)
    char_budget = 12000
    if len(raw) > char_budget:
        half = char_budget // 2
        raw = raw[:half] + "\n...[middle compressed]...\n" + raw[-half:]

    print(f"[skill-from-memopipe] Analysing {len(rows)} captures from last {hours}h...")

    result = ask_ai(
        "You are a skill-detection agent reviewing a person's recent computer activity.\n"
        "Identify 1-3 REPEATABLE thinking patterns or workflows the person appears to be doing frequently.\n"
        "A repeatable skill is: something they do again and again, not a one-off task.\n"
        "For each candidate, output exactly:\n"
        "CANDIDATE: <kebab-case-slug>\n"
        "DESCRIPTION: <one sentence — what is the repeatable thing>\n"
        "EVIDENCE: <one sentence — what in the captures suggests it is repeatable>\n"
        "WORTH_PACKAGING: yes/no — is this distinct enough from common knowledge to be a real skill?\n\n"
        "If nothing repeatable is visible, output: NO_CANDIDATES\n\n"
        f"CAPTURES (last {hours}h):\n{raw}"
    )

    if "NO_CANDIDATES" in result.upper():
        print(f"No repeatable skill patterns detected in the last {hours}h captures.")
        return

    print("\n--- Skill candidates detected ---")
    print(result)
    print("\nFor each candidate you want to capture:")
    print("  python vault_intelligence.py skill-capture \"<description of the pattern>\"")
    print("Then audit it:")
    print("  python vault_intelligence.py skill-audit <slug>")


def run_skill_audit(slug: str) -> None:
    """Run debt-prevention pre-registration audit on a skill draft in Memory/Skills/."""
    vault = Path(VAULT_PATH)
    skills_dir = vault / "Memory" / "Skills"

    skill_dir = skills_dir / slug
    if not skill_dir.exists():
        candidates = (
            [d for d in skills_dir.iterdir() if d.is_dir() and slug.lower() in d.name.lower()]
            if skills_dir.exists()
            else []
        )
        if len(candidates) == 1:
            skill_dir = candidates[0]
        elif len(candidates) > 1:
            print(f"Multiple matches: {[d.name for d in candidates]}")
            return
        else:
            print(f"Skill not found: {slug!r} in {skills_dir}")
            return

    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        print(f"No SKILL.md in {skill_dir}")
        return

    skill_text = skill_path.read_text(encoding="utf-8")

    other_skills: list[str] = []
    if skills_dir.exists():
        for other in skills_dir.iterdir():
            if other.is_dir() and other != skill_dir:
                sp = other / "SKILL.md"
                if sp.exists():
                    other_skills.append(f"=== {other.name} ===\n{sp.read_text(encoding='utf-8')[:600]}")

    overlap_context = (
        "\n\nEXISTING SKILLS IN BANK:\n" + "\n".join(other_skills[:6])
        if other_skills
        else "\n\nNo other skills in bank yet."
    )

    print(f"[skill-audit] Auditing: {skill_dir.name}")
    print("Running: generalization test + pre-mortem + overlap check...")

    result = ask_ai(
        "You are a skill debt-prevention auditor. Audit this skill candidate before it is registered.\n\n"
        "Run three checks:\n\n"
        "1. GENERALIZATION TEST\n"
        "   - What task or context was this skill likely created from?\n"
        "   - Name 2 different contexts where it should also apply.\n"
        "   - Does the SKILL.md procedure work on those contexts, or does it bake in narrow assumptions?\n"
        "   - List any specific lines that encode trajectory-specific assumptions.\n\n"
        "2. PRE-MORTEM\n"
        "   - 'Assume this skill fails or causes harm in 6-12 months. Why?'\n"
        "   - List every plausible failure mode.\n"
        "   - For each: is it visible before it causes harm? Does the test suite catch it?\n\n"
        "3. OVERLAP CHECK\n"
        "   - Does any existing skill in the bank cover >30% of the same ground?\n"
        "   - If yes: recommend MERGE or keep both with explicit boundary documentation.\n\n"
        "End with:\n"
        "VERDICT: APPROVE / CONDITIONAL / REJECT\n"
        "REQUIRED_CHANGES: (list if CONDITIONAL) or NONE\n\n"
        f"SKILL CANDIDATE:\n{skill_text}\n"
        f"{overlap_context}"
    )

    print("\n--- Audit Result ---")
    print(result)

    verdict_line = next(
        (line for line in result.splitlines() if line.startswith("VERDICT:")),
        "VERDICT: unknown"
    )
    date_str = datetime.now().strftime("%Y-%m-%d")
    memory_path = skill_dir / ".memory.md"
    if not memory_path.exists():
        memory_path.write_text(f"# Memory: {skill_dir.name}\n\n## Observations\n\n", encoding="utf-8")

    with memory_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## Audit — {date_str}\n\n")
        f.write(f"**{verdict_line}**\n\n")
        f.write("```\n" + result[:1200] + "\n```\n")

    print(f"\nAudit logged to {skill_dir.name}/.memory.md")
    if "APPROVE" in verdict_line.upper():
        print("Skill is ready. Update status: active in SKILL.md frontmatter.")
    elif "CONDITIONAL" in verdict_line.upper():
        print("Address REQUIRED_CHANGES, then re-run skill-audit.")
    else:
        print("Skill rejected. Consider reworking or merging with an existing skill.")


def _build_inlink_counts(skill_slugs: list[str], vault: Path) -> dict[str, int]:
    """Single-pass vault scan: count unique notes that wikilink to each skill slug."""
    counts: dict[str, int] = {slug: 0 for slug in skill_slugs}
    slugs_lower = [s.lower() for s in skill_slugs]
    for md in vault.rglob("*.md"):
        if _should_skip_path(md, vault):
            continue
        if "Skills" in md.parts:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        found_here: set[str] = set()
        for m in _WIKILINK_RE.finditer(text):
            raw = m.group(1).lower()
            for slug, slug_l in zip(skill_slugs, slugs_lower):
                if slug not in found_here and slug_l in raw:
                    counts[slug] += 1
                    found_here.add(slug)
    return counts


def run_swarm_dashboard() -> None:
    """Compute swarm colony stats and write Memory/Swarm-Dashboard.md."""
    vault = Path(VAULT_PATH)
    skills_dir = vault / "Memory" / "Skills"

    if not skills_dir.exists():
        print("No Memory/Skills/ directory found. Use skill-capture first.")
        return

    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d %H:%M")

    skill_data: list[dict] = []
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

        fm: dict[str, str] = {}
        in_fm = False
        for line in text.splitlines():
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                    continue
                break
            if in_fm and ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"')

        title = skill_dir.name
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        use_count = int(fm.get("use_count", "0") or "0")
        last_used_str = fm.get("last_used", "")
        created_str = fm.get("created", "")
        revalidate = fm.get("revalidate_after", "—")

        if last_used_str:
            try:
                last_used_dt = datetime.strptime(last_used_str[:10], "%Y-%m-%d")
                days_stale = (today - last_used_dt).days
            except ValueError:
                days_stale = 999
        else:
            days_stale = 999

        fitness = (
            0.0 if use_count == 0
            else round(use_count * math.exp(-days_stale / 30), 3)
        )

        skill_data.append({
            "slug": skill_dir.name,
            "title": title,
            "path": str(skill_path.relative_to(vault)).replace("\\", "/"),
            "use_count": use_count,
            "days_stale": days_stale,
            "last_used": last_used_str or "never",
            "created": created_str,
            "revalidate": revalidate,
            "fitness": fitness,
        })

    if not skill_data:
        print("No skills found. Use skill-capture first.")
        return

    print(f"Scanning vault for pheromone trails ({len(skill_data)} skills)…")
    trail_counts = _build_inlink_counts([s["slug"] for s in skill_data], vault)
    for s in skill_data:
        s["trails"] = trail_counts.get(s["slug"], 0)

    skill_data.sort(key=lambda x: (-x["fitness"], -x["use_count"], x["days_stale"]))

    total_uses = sum(s["use_count"] for s in skill_data)
    stale = [s for s in skill_data if s["days_stale"] > 30]
    scouts = [s for s in skill_data if s["use_count"] == 0]
    gbest = next((s for s in skill_data if s["fitness"] > 0), None)

    projects_dir = vault / "Memory" / "Active Projects"
    active_projects: list[tuple[str, str, str]] = []
    if projects_dir.exists():
        for p in sorted(projects_dir.glob("*.md")):
            if p.name.startswith("."):
                continue
            rel = str(p.relative_to(vault)).replace("\\", "/")
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
            active_projects.append((p.stem, rel, mtime))

    def _skill_link(s: dict) -> str:
        return f"[[{s['path']}\\|{s['title']}]]"

    lines = [
        "---",
        "type: dashboard",
        f"generated: {date_str}",
        "---",
        "",
        "# Swarm Colony Dashboard",
        "",
        f"> **Generated:** {date_str}  ·  Refresh: `python vault_intelligence.py swarm-dashboard`",
        "> Fitness = `use_count × e^(−days_stale/30)` — exponential pheromone decay (ACO).",
        "> Pheromone trails = incoming wikilinks from other notes (stigmergy).",
        "",
        "---",
        "",
        "## Colony State",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Particles (skills) | {len(skill_data)} |",
        f"| Colony momentum (total uses) | {total_uses} |",
        f"| Evaporating (>30 days stale) | {len(stale)} |",
        f"| Scouts (never used) | {len(scouts)} |",
        (
            f"| Global best (gbest) | {_skill_link(gbest)} — fitness {gbest['fitness']} |"
            if gbest else
            "| Global best (gbest) | — no used skills yet |"
        ),
        "",
        "---",
        "",
        "## Fitness Leaderboard",
        "",
        "> Fitness decays exponentially with disuse. A skill used yesterday scores 37× higher",
        "> than one unused for 30 days at the same use_count.",
        "",
        "| Skill | Uses | Days Stale | Fitness | Trails | Signal |",
        "|-------|------|-----------|---------|--------|--------|",
    ]
    for s in skill_data:
        signal = (
            "🌟 peak"  if s["fitness"] > 5 else
            "✨ warm"  if s["fitness"] > 1 else
            "💫 faint" if s["use_count"] > 0 else
            "🔵 linked" if s["trails"] > 0 else
            "⚫ dark"
        )
        stale_str = "—" if s["days_stale"] == 999 else str(s["days_stale"])
        fit_str = str(s["fitness"]) if s["fitness"] > 0 else "—"
        lines.append(
            f"| {_skill_link(s)} | {s['use_count']} | {stale_str} | {fit_str} | {s['trails']} | {signal} |"
        )

    lines += ["", "---", "", "## Evaporation Alerts", ""]
    if stale:
        lines += [
            "> Run `skill-log <slug> \"...\"` to refresh, or delete the folder to kill.",
            "",
            "| Skill | Days Stale | Uses | Revalidate After |",
            "|-------|-----------|------|-----------------|",
        ]
        for s in sorted(stale, key=lambda x: -x["days_stale"]):
            stale_str = "—" if s["days_stale"] == 999 else str(s["days_stale"])
            lines.append(
                f"| {_skill_link(s)} | {stale_str} | {s['use_count']} | {s['revalidate']} |"
            )
    else:
        lines.append("✅ No evaporating skills — colony is active.")

    lines += ["", "---", "", "## Scout Candidates", ""]
    if scouts:
        lines += [
            "> ABC: scouts have never been used. Assign one to your next task.",
            "",
            "| Skill | Created | Revalidate After |",
            "|-------|---------|-----------------|",
        ]
        for s in scouts:
            lines.append(f"| {_skill_link(s)} | {s['created'] or '—'} | {s['revalidate']} |")
    else:
        lines.append("✅ All skills have been used at least once.")

    trail_sorted = sorted(skill_data, key=lambda x: (-x["trails"], -x["use_count"]))
    lines += [
        "",
        "---",
        "",
        "## Pheromone Trail Map",
        "",
        "> Ranked by incoming wikilinks. Zero-trail skills are invisible to the colony.",
        "> Link to a skill from any note you write to strengthen its trail.",
        "",
        "| Skill | Incoming Links | Uses | Action |",
        "|-------|---------------|------|--------|",
    ]
    for s in trail_sorted:
        action = (
            "⚠️ link from a note" if s["trails"] == 0 else
            "→ add more links"    if s["trails"] < 3 else
            "✓"
        )
        lines.append(f"| {_skill_link(s)} | {s['trails']} | {s['use_count']} | {action} |")

    lines += ["", "---", "", "## Active Food Sources", ""]
    if active_projects:
        lines += [
            "> Projects the colony is currently exploiting.",
            "",
            "| Project | Last Modified |",
            "|---------|-------------|",
        ]
        for stem, rel, mtime in active_projects:
            lines.append(f"| [[{rel}\\|{stem}]] | {mtime} |")
    else:
        lines.append("No active projects. Run `promote` to create one from Open-Loops.")

    lines += ["", "---", "", "## Skill Velocity", ""]
    by_month: dict[str, int] = {}
    for s in skill_data:
        if s["created"] and len(s["created"]) >= 7:
            month = s["created"][:7]
            by_month[month] = by_month.get(month, 0) + 1
    if by_month:
        lines += ["| Month | Skills Added |", "|-------|-------------|"]
        for month in sorted(by_month):
            n = by_month[month]
            lines.append(f"| {month} | {'█' * n} ({n}) |")
    else:
        lines.append("No creation dates recorded.")

    lines += [
        "",
        "---",
        "",
        "*Refresh: `python vault_intelligence.py swarm-dashboard`*",
        "*Upgrade to live queries: install the [Dataview plugin](https://github.com/blacksmithgu/obsidian-dataview)*",
        "*then open `Memory/Swarm-Dashboard-Live.md` (the DataviewJS version).*",
    ]

    out_path = vault / "Memory" / "Swarm-Dashboard.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Swarm dashboard written: {out_path}")
    print(
        f"  {len(skill_data)} skills  ·  momentum {total_uses}  ·  "
        f"{len(stale)} evaporating  ·  {len(scouts)} scouts"
    )
    if gbest:
        print(f"  Global best: {gbest['title']} (fitness {gbest['fitness']})")
