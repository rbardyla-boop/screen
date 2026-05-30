"""
vault_ai.py — AI-assisted knowledge commands (link, promote, connections, ask, etc.)

Commands exposed via vault_intelligence.py:
  link, promote, inbox, connections, ask, write-prep, contradict, synthesize
"""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ai_provider import ask_ai
from vault_skills import _make_slug

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")

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


def _should_skip_path(p: Path, vault: Path) -> bool:
    try:
        rel = str(p.relative_to(vault)).lower()
    except ValueError:
        rel = str(p).lower()
    return any(bad.lower() in rel for bad in _NEVER_SCAN)


def _search_vault_notes(
    query: str,
    search_dir: Path,
    vault: Path,
    top_n: int = 8,
    snippet_len: int = 1500,
) -> list[tuple[str, str]]:
    """Return [(rel_path, snippet)] for the top-n notes most relevant to query keywords."""
    keywords = [w.lower() for w in query.split() if len(w) > 3]
    if not keywords:
        return []

    scored: list[tuple[int, str, str]] = []
    for md in search_dir.rglob("*.md"):
        if _should_skip_path(md, vault):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        score = sum(kw in text.lower() for kw in keywords)
        if score > 0:
            rel = str(md.relative_to(vault))
            scored.append((score, rel, text[:snippet_len]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(rel, text) for _, rel, text in scored[:top_n]]


def run_link(note_arg: str) -> None:
    vault = Path(VAULT_PATH)
    note = Path(note_arg) if Path(note_arg).is_absolute() else vault / note_arg
    if not note.exists():
        print(f"Note not found: {note}")
        sys.exit(1)

    note_text = note.read_text(encoding="utf-8", errors="ignore")
    all_titles: list[str] = [
        str(md.relative_to(vault).with_suffix(""))
        for md in vault.rglob("*.md")
        if md != note and "Archive" not in md.parts
    ]
    titles_block = "\n".join(f"- {t}" for t in all_titles[:500])

    prompt = (
        "You are an Obsidian knowledge-base assistant. Given a note and a list of other note "
        "titles in the vault, identify the 3 to 5 titles that are most semantically related to "
        "the note's content. For each, provide a one-sentence explanation of the conceptual bridge "
        "between the two.\n\n"
        "Format your response ONLY as a Markdown bullet list like this:\n"
        "- [[Title of Note]]: One-sentence explanation.\n\n"
        f"Note content:\n{note_text[:8000]}\n\n"
        f"All other note titles:\n{titles_block}"
    )

    print("Asking AI to find connections…")
    connections = ask_ai(prompt)

    existing = note_text
    section_header = "\n\n## AI Suggested Connections\n\n"
    cut_index = existing.find(section_header)
    if cut_index != -1:
        existing = existing[:cut_index]

    note.write_text(existing + section_header + connections + "\n", encoding="utf-8")
    print(f"Connections appended to: {note}")


def run_inbox_processor() -> None:
    """
    Process top-level markdown files in 00_Inbox/:
    - LITERATURE → Memory/Literature/
    - CONCEPT    → Memory/Permanent/
    - PROJECT    → appended to Open-Loops.md, then archived
    - SKIP       → archived without processing
    """
    vault = Path(VAULT_PATH)
    inbox = vault / "00_Inbox"

    if not inbox.exists():
        print("No 00_Inbox/ folder found.")
        return

    processed_dir = inbox / "Processed"
    processed_dir.mkdir(exist_ok=True)

    md_files = [
        f for f in inbox.iterdir()
        if f.is_file() and f.suffix == ".md" and not _should_skip_path(f, vault)
    ]

    if not md_files:
        print("No markdown files in 00_Inbox/ to process.")
        return

    print(f"Found {len(md_files)} file(s) in 00_Inbox/\n")
    loops_path = vault / "Memory" / "Open-Loops.md"

    for md in md_files:
        text = md.read_text(encoding="utf-8", errors="ignore")[:4000]
        result = ask_ai(
            "Classify this inbox note into exactly one category:\n"
            "LITERATURE — summarizes or quotes an external source\n"
            "CONCEPT    — captures an idea or insight worth a permanent note\n"
            "PROJECT    — describes work to be done or an open loop\n"
            "SKIP       — too vague or short to keep\n\n"
            "Response format (two lines only):\n"
            "CATEGORY: <LITERATURE|CONCEPT|PROJECT|SKIP>\n"
            "SUMMARY: <2 sentences>\n\n"
            f"Note filename: {md.name}\n"
            f"Note content:\n{text}"
        )

        category, summary = "SKIP", ""
        for line in result.splitlines():
            if line.startswith("CATEGORY:"):
                category = line.split(":", 1)[1].strip().upper()
            elif line.startswith("SUMMARY:"):
                summary = line.split(":", 1)[1].strip()

        print(f"  {md.name}")
        print(f"  → {category}: {summary}")

        if category == "LITERATURE":
            dest = vault / "Memory" / "Literature" / md.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            md.rename(dest)
            print(f"     Moved to Memory/Literature/")
        elif category == "CONCEPT":
            dest = vault / "Memory" / "Permanent" / md.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            md.rename(dest)
            print(f"     Moved to Memory/Permanent/")
        elif category == "PROJECT":
            loops_path.parent.mkdir(parents=True, exist_ok=True)
            with loops_path.open("a", encoding="utf-8") as f:
                f.write(f"\n- {md.stem}: {summary}\n")
            md.rename(processed_dir / md.name)
            print(f"     Appended to Open-Loops.md, archived")
        else:
            md.rename(processed_dir / md.name)
            print(f"     Archived without processing")
        print()

    print("Inbox processing complete.")


def run_connections(days: int = 7) -> None:
    """
    Find non-obvious connections between recently modified Memory/ notes
    and all other vault notes. Saves a report to Memory/.
    """
    vault = Path(VAULT_PATH)
    memory_dir = vault / "Memory"
    if not memory_dir.exists():
        print("No Memory/ folder found.")
        return

    cutoff = time.time() - (days * 86400)
    skip_names = {"Unfinished Work Dashboard.md", "Open-Loops.md"}
    recent = [
        md for md in memory_dir.rglob("*.md")
        if (
            md.stat().st_mtime > cutoff
            and not _should_skip_path(md, vault)
            and md.name not in skip_names
        )
    ][:8]

    if not recent:
        print(f"No notes modified in the last {days} days in Memory/.")
        return

    print(f"Found {len(recent)} recently modified note(s). Scanning for connections...")

    all_notes: list[str] = []
    recent_set = set(recent)
    for md in sorted(memory_dir.rglob("*.md")):
        if _should_skip_path(md, vault) or md in recent_set:
            continue
        try:
            snippet = md.read_text(encoding="utf-8", errors="ignore")[:250]
            rel = str(md.relative_to(vault))
            all_notes.append(f"[[{rel}]]: {snippet}")
        except Exception:
            continue

    recent_block = "\n\n".join(
        f"=== [[{md.relative_to(vault)}]] ===\n"
        + md.read_text(encoding="utf-8", errors="ignore")[:800]
        for md in recent
    )

    result = ask_ai(
        "You are a knowledge connection finder for a personal second brain.\n\n"
        "For each recently modified note below, find 2-3 NON-OBVIOUS connections "
        "to the vault index. Skip connections obvious from shared keywords. "
        "Focus on structural, thematic, or causal links the author probably hasn't noticed.\n\n"
        "Format:\n"
        "### [[recently-modified-note-path]]\n"
        "- [[other-note]]: one sentence on the non-obvious connection\n\n"
        f"RECENTLY MODIFIED NOTES:\n{recent_block}\n\n"
        f"VAULT INDEX:\n" + "\n\n".join(all_notes[:200])
    )

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = memory_dir / f"Connections-{date_str}.md"
    out_path.write_text(
        f"# Connection Report — {date_str}\n\n"
        f"*Notes modified in the last {days} days*\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"Connections report written: {out_path}")


def run_ask(question: str) -> None:
    """Answer a question by grounding in vault notes first, then surfacing gaps."""
    vault = Path(VAULT_PATH)
    hits = _search_vault_notes(question, vault / "Memory", vault, top_n=6)

    if not hits:
        print("No relevant notes found in vault. Answering from general knowledge.\n")
        print(ask_ai(question))
        return

    vault_context = "\n\n---\n\n".join(
        f"From [[{rel}]]:\n{snippet}" for rel, snippet in hits
    )
    print(f"Found {len(hits)} relevant note(s).\n")
    print(ask_ai(
        f"Answer this question using the person's own knowledge vault first.\n\n"
        f"QUESTION: {question}\n\n"
        f"THEIR VAULT NOTES ({len(hits)} relevant):\n{vault_context}\n\n"
        f"## From your vault\n"
        f"[Answer grounded in their notes, with [[note]] citations]\n\n"
        f"## Gaps in your notes\n"
        f"[What's missing that would help answer more completely]\n\n"
        f"## Additional context\n"
        f"[External knowledge only if genuinely needed, clearly labeled]"
    ))


def run_write_prep(topic: str) -> None:
    """Find vault notes on a topic and produce a structured writing prep document."""
    vault = Path(VAULT_PATH)
    hits = _search_vault_notes(topic, vault / "Memory", vault, top_n=8, snippet_len=2000)

    if not hits:
        print(f"No notes found in vault related to '{topic}'.")
        return

    vault_context = "\n\n---\n\n".join(
        f"From [[{rel}]]:\n{snippet}" for rel, snippet in hits
    )
    print(f"Found {len(hits)} relevant note(s). Building write prep...")
    result = ask_ai(
        f"Help prepare to write about: {topic}\n\n"
        f"VAULT NOTES ({len(hits)} relevant):\n{vault_context}\n\n"
        f"## Strongest argument your notes support\n"
        f"[One paragraph — what claim the evidence actually supports]\n\n"
        f"## Key evidence from vault\n"
        f"[Bulleted list with [[note]] citations]\n\n"
        f"## Counterarguments raised by your notes\n"
        f"[What your own vault pushes back on]\n\n"
        f"## Connections worth making explicit\n"
        f"[Links between notes that would strengthen the piece]\n\n"
        f"## Research gaps\n"
        f"[What's missing before writing]\n\n"
        f"## Suggested structure\n"
        f"[3-5 section outline based only on vault evidence]"
    )

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = vault / "Memory" / "Outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"write-prep-{_make_slug(topic, 50).lower()}-{date_str}.md"
    out_path.write_text(
        f"# Write Prep: {topic}\n\n*{date_str} · {len(hits)} vault notes*\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"Write prep saved: {out_path}")


def run_contradict() -> None:
    """Surface contradictory positions across permanent/Memory notes."""
    vault = Path(VAULT_PATH)
    perm_dir = vault / "Memory" / "Permanent"
    search_dir = perm_dir if perm_dir.exists() else vault / "Memory"

    skip_names = {"Unfinished Work Dashboard.md", "Open-Loops.md"}
    notes: list[tuple[str, str]] = []
    for md in sorted(search_dir.rglob("*.md")):
        if _should_skip_path(md, vault) or md.name in skip_names:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        notes.append((str(md.relative_to(vault)), text[:1000]))

    if len(notes) < 3:
        print(f"Only {len(notes)} note(s) found. Need at least 3 for a useful contradiction check.")
        return

    notes_block = "\n\n---\n\n".join(
        f"[[{rel}]]:\n{text}" for rel, text in notes[:30]
    )
    print(f"Checking {len(notes)} note(s) for contradictions...\n")
    print(ask_ai(
        "You are an intellectual consistency auditor for a personal knowledge vault.\n\n"
        "Read these notes and find any places where the author holds contradictory or "
        "inconsistent positions. Different framings of the same idea do not count.\n\n"
        "For each real contradiction:\n"
        "- Name both notes\n"
        "- Quote the specific conflicting claims\n"
        "- Frame it as a question the author must resolve\n\n"
        "If no real contradictions exist, say so clearly.\n\n"
        f"NOTES ({len(notes)} total, showing first 30):\n{notes_block}"
    ))


def run_synthesize(topic: str) -> None:
    """Generate a synthesis from all vault notes related to a topic."""
    vault = Path(VAULT_PATH)
    hits = _search_vault_notes(topic, vault / "Memory", vault, top_n=12, snippet_len=3000)

    if not hits:
        print(f"No notes found in vault related to '{topic}'.")
        return

    if len(hits) < 3:
        print(f"Only {len(hits)} note(s) on '{topic}'. Synthesis is most useful with 5+. Proceeding anyway.")

    vault_context = "\n\n---\n\n".join(
        f"From [[{rel}]]:\n{text}" for rel, text in hits
    )
    print(f"Found {len(hits)} note(s) on '{topic}'. Generating synthesis...")
    result = ask_ai(
        f"Synthesize everything in this personal vault about: {topic}\n\n"
        f"VAULT NOTES ({len(hits)} total):\n{vault_context}\n\n"
        f"Produce a synthesis that could ONLY exist by reading all notes together — "
        f"not what any single note says. Use [[note]] citations throughout.\n\n"
        f"## Central claim\n"
        f"[What the notes collectively support — stated as a single strong claim]\n\n"
        f"## Evidence, organized\n"
        f"[Hierarchical: strongest first, with [[note]] citations]\n\n"
        f"## Tensions and open questions\n"
        f"[Where the notes contradict or leave gaps]\n\n"
        f"## Next questions worth investigating\n"
        f"[Three most important things to research next]"
    )

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = vault / "Memory" / "Outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_make_slug(topic, 50).lower()}-synthesis-{date_str}.md"
    out_path.write_text(
        f"# Synthesis: {topic}\n\n*{date_str} · {len(hits)} vault notes*\n\n{result}\n",
        encoding="utf-8",
    )
    print(f"Synthesis saved: {out_path}")


def run_promote() -> None:
    """
    Interactive: pick an item from Open-Loops.md and promote it as:
    1. Project    → Memory/Active Projects/<slug>.md
    2. Concept    → Memory/Permanent/<slug>.md (AI-refined permanent note)
    3. Literature → Memory/Literature/<slug>.md (source capture template)
    """
    vault = Path(VAULT_PATH)
    open_loops_path = vault / "Memory" / "Open-Loops.md"

    if not open_loops_path.exists():
        print("Memory/Open-Loops.md not found. Nothing to promote.")
        return

    text = open_loops_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    items: list[tuple[int, str]] = [
        (i, line.strip())
        for i, line in enumerate(lines)
        if line.strip().startswith("- ") and len(line.strip()) > 3
    ]

    if not items:
        print("No bullet items found in Memory/Open-Loops.md.")
        return

    print("\nOpen loops (pick a number to promote):\n")
    for idx, (_, item) in enumerate(items, 1):
        print(f"  {idx:>2}. {item}")

    print()
    try:
        choice = int(input("Promote item #: ").strip())
        if choice < 1 or choice > len(items):
            print("Invalid choice.")
            return
    except (ValueError, EOFError):
        print("Cancelled.")
        return

    line_idx, chosen = items[choice - 1]
    title = chosen.lstrip("- ").strip()
    slug = _make_slug(title)
    date_str = datetime.now().strftime("%Y-%m-%d")

    print("\nPromote as:")
    print("  1. Project    → Memory/Active Projects/  (task, next-action oriented)")
    print("  2. Concept    → Memory/Permanent/         (idea/insight, AI-refined)")
    print("  3. Literature → Memory/Literature/        (source capture, fill manually)")
    print()
    try:
        kind = int(input("Type (1/2/3): ").strip())
        if kind not in (1, 2, 3):
            print("Invalid choice.")
            return
    except (ValueError, EOFError):
        print("Cancelled.")
        return

    if kind == 1:
        dest_dir = vault / "Memory" / "Active Projects"
        dest_dir.mkdir(parents=True, exist_ok=True)
        note_path = dest_dir / f"{slug}.md"
        note_path.write_text(
            f"# {title}\n\n"
            "## Why this matters\n\n\n\n"
            "## Next action\n\n- [ ] \n\n"
            "## Notes\n\n",
            encoding="utf-8",
        )
        print(f"\nCreated: {note_path.relative_to(vault)}")
        print("Fill in 'Why this matters' and 'Next action' now, or it evaporates again.")

    elif kind == 2:
        dest_dir = vault / "Memory" / "Permanent"
        dest_dir.mkdir(parents=True, exist_ok=True)
        note_path = dest_dir / f"{slug}.md"

        print("\nAI refining into permanent note format...")
        refined = ask_ai(
            f"Turn this raw idea into a permanent note seed for a second brain.\n"
            f"Raw idea: {title}\n\n"
            f"Write as if the author is explaining it to themselves. Keep it under 180 words.\n"
            f"Structure (no headers, just prose + a short list):\n"
            f"1. What this concept means in plain language (2-3 sentences)\n"
            f"2. Why it matters for the author's thinking\n"
            f"3. 2-3 Obsidian [[wikilink]] suggestions for concepts to connect\n"
            f"4. One open question this idea raises\n\n"
            f"Do not add a title or section headers."
        )
        note_path.write_text(
            f"---\ntype: permanent\ncreated: {date_str}\n---\n\n"
            f"# {title}\n\n"
            f"{refined}\n\n"
            f"## Source\nPromoted from [[Memory/Open-Loops]]\n",
            encoding="utf-8",
        )
        print(f"\nCreated: {note_path.relative_to(vault)}")
        print("Review the AI draft — it's a seed, not a finished note.")

    elif kind == 3:
        dest_dir = vault / "Memory" / "Literature"
        dest_dir.mkdir(parents=True, exist_ok=True)
        note_path = dest_dir / f"{slug}.md"
        note_path.write_text(
            f"---\ntype: literature\nsource: \nauthor: \ndate_read: {date_str}\nstatus: unprocessed\n---\n\n"
            f"# {title}\n\n"
            f"## The Core Argument\n\n\n\n"
            f"## Key Evidence\n\n- \n\n"
            f"## My Reaction\n\n\n\n"
            f"## Notes to Process\n\n- \n",
            encoding="utf-8",
        )
        print(f"\nCreated: {note_path.relative_to(vault)}")
        print("Fill in the source details and your reaction before this note evaporates.")

    new_lines = [line for i, line in enumerate(lines) if i != line_idx]
    open_loops_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Removed from Open-Loops.md.")
