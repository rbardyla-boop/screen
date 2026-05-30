# Role: Obsidian Vault Chief of Staff

You have full read/write access to this local Markdown vault.
Scripts live in the `vault-scripts/` folder next to the vault.
Always activate the venv before running scripts:

```bash
source vault-scripts/.venv/bin/activate
```

---

## Task 1: Daily Screen Summary + Open Loop Detection

Runs at the end of the day. Does two AI passes on today's OCR/audio:
1. Summarises what you watched/read → `Daily_Summaries/YYYY-MM-DD.md` + Word doc
2. Extracts unfinished intentions → appends to `Memory/Open-Loops.md`

```bash
python vault-scripts/Screenpipe-to-Obsidian.py
```

After running, open `Memory/Open-Loops.md` to see what Screenpipe caught you starting and not finishing.

---

## Task 2: Inbox Ingestion (file watcher)

Drop any `.pdf`, `.docx`, `.doc`, `.odt`, or `.rtf` into `00_Inbox/`.
The watcher converts it to Markdown and moves the original to `00_Inbox/Archive/`.

```bash
python vault-scripts/vault_watcher.py
```

Run this once in a background terminal to keep it active all day.

---

## Task 3: Gap Analysis — Your Actual Memory System (Unfinished Work)

**This is the only part of the system that matters for your stated goal.**

After the 2026-05-28 near-death experience (48GB tar pit caused by dumping dev projects into the vault), the system now has **ruthless enforcement**.

### The single command you should run every day:

```bash
memory-check
```

This does:
1. Runs the vault guard (hard fails + refuses to proceed if you are repeating the old bloat patterns)
2. Regenerates `Memory/Unfinished Work Dashboard.md` from the high-signal Memory/ core only
3. Shows you the current state of the sacred surface

### Manual (if you must)

```bash
python vault-scripts/vault_intelligence.py gaps --scope Memory
```

**Never** run without `--scope Memory` (or equivalent). Full-vault scans are now intentionally dangerous and will be blocked by the guard in most cases.

See `Memory/RULES_RUTHLESS.md` inside the vault. Read it. Internalize it. The rules exist because you have already proven you cannot be trusted without them.

---

## Task 4: Promote an Open Loop

When you see something in `Memory/Open-Loops.md` worth committing to, promote it:

```bash
python vault-scripts/vault_intelligence.py promote
```

Shows a numbered list of your open loops and lets you pick one. Then asks which type:

- **Project** → `Memory/Active Projects/<slug>.md` with next-action template
- **Concept** → `Memory/Permanent/<slug>.md` — AI refines the raw idea into a permanent note seed
- **Literature** → `Memory/Literature/<slug>.md` — blank source capture template to fill manually

---

## Task 5: Connection Mapping

Reads one note and appends an `## AI Suggested Connections` section linking to
the 3–5 most semantically related notes already in the vault.

```bash
python vault-scripts/vault_intelligence.py link "Daily_Summaries/2026-05-20.md"
```

---

## Task 6: Inbox Processor

Classifies top-level markdown files in `00_Inbox/` and routes them to the right Memory/ subfolder.

```bash
python vault-scripts/vault_intelligence.py inbox
```

- LITERATURE → `Memory/Literature/`
- CONCEPT → `Memory/Permanent/`
- PROJECT → appended to `Open-Loops.md`, then archived
- SKIP → archived without processing

---

## Task 7: Connection Finder (weekly)

Finds non-obvious connections between recently modified Memory/ notes and the rest of the vault.

```bash
python vault-scripts/vault_intelligence.py connections
python vault-scripts/vault_intelligence.py connections --days 14
```

Saves a `Memory/Connections-YYYY-MM-DD.md` report. Run weekly.

---

## Task 8: Ask a Question

Searches your vault notes first, then answers. Shows what gaps exist in your notes.

```bash
python vault-scripts/vault_intelligence.py ask "what do I think about attention mechanisms"
```

---

## Task 9: Write Prep

Finds vault notes on a topic and builds a structured writing prep document.

```bash
python vault-scripts/vault_intelligence.py write-prep "transformer architectures"
```

Saves to `Memory/Outputs/write-prep-<topic>-<date>.md`.

---

## Task 10: Contradiction Detector (monthly)

Reads your permanent/Memory notes and surfaces contradictory positions you hold.

```bash
python vault-scripts/vault_intelligence.py contradict
```

---

## Task 11: Synthesize

Synthesizes all vault notes on a topic into a single document that only exists by reading them together.

```bash
python vault-scripts/vault_intelligence.py synthesize "machine learning"
```

Saves to `Memory/Outputs/<topic>-synthesis-<date>.md`. Most useful when you have 5+ notes on a topic.

---

## Task 12: Skill Capture — Turn Captures Into Reusable Skills

When Screenpipe surfaces something in Open-Loops.md and it looks like a repeatable workflow, promote it to the skill bank:

```bash
python vault_intelligence.py skill-capture
# (paste raw text, then Ctrl+D)

# or inline:
python vault_intelligence.py skill-capture "I keep doing X every time I need to Y..."
```

Creates `Memory/Skills/<slug>/SKILL.md` + `.memory.md`. Open the SKILL.md in Obsidian and refine the trigger and steps — the AI draft is a seed.

The skill bank lives at `Memory/Skills/`. Skills not used in 30 days are automatically surfaced in the Unfinished Work Dashboard (no extra command needed).

---

## Task 13: Skill Log — Record Observations

After using a skill, log what happened:

```bash
python vault_intelligence.py skill-log skill-capture-pipeline "Used it after screenpipe caught me in a rabbit hole. Steps 1-3 worked. Step 4 skipped — I refined it immediately instead."
```

Appends to `Memory/Skills/<slug>/.memory.md` and updates `last_used` + `use_count` in the frontmatter. This is how skills get smarter instead of rotting.

---

## Automation (optional)

Add a cron job to run the daily summary automatically at 11:55 PM:

```
55 23 * * * /home/yourname/vault-scripts/.venv/bin/python /home/yourname/vault-scripts/Screenpipe-to-Obsidian.py
```

Weekly connection finder (every Sunday at 9am):

```
0 9 * * 0 /home/yourname/vault-scripts/.venv/bin/python /home/yourname/vault-scripts/vault_intelligence.py connections
```

Monthly contradiction check (1st of month at 9am):

```
0 9 1 * * /home/yourname/vault-scripts/.venv/bin/python /home/yourname/vault-scripts/vault_intelligence.py contradict
```

Edit with: `crontab -e`
