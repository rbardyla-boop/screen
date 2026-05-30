# POST-MORTEM: Second Brain Near-Death Experience — 2026-05-28

## What Happened (First Principles)

You turned your Obsidian vault — whose entire purpose was to be a fast, high-signal external memory for the specific defect "I start things and then forget they exist" — into a general-purpose filesystem dump for every project, venv, automation pipeline, video render, and half-baked experiment on your machine.

The single largest folder (`00_Inbox/grok/`) reached ~46 GB with tens of thousands of files that Obsidian had no business indexing.

Result:
- Sync that ran for hours and never completed
- Obsidian that could not practically open or search the vault
- Complete loss of the "second brain" function
- Anxiety and paralysis instead of clarity

This was not a tooling failure. This was a **discipline failure** that the tools then amplified.

## Root Cause

The `00_Inbox/` was designed as a *temporary airlock* for document conversion (PDFs → Markdown via the watcher).

You used it as a trash can for active development workspaces.

The watcher had zero defenses. The daily tools had zero awareness. There was no enforcement layer.

You (correctly) diagnosed that you needed a memory system for unfinished work. Then you built the exact opposite of that.

## What Was Done (Ruthless Surgical Response)

1. **Eviction** — ~45+ GB of toxic dev material moved to:
   `~/Projects/legacy-from-obsidian-vault/2026-05-28/`
   With brutal manifest and pointer left behind in the vault.

2. **New sacred core** — `Memory/` folder created as the *only* thing that should stay small, fast, and always open. Contains:
   - Unfinished Work Dashboard (regenerated from high-signal sources only)
   - Open-Loops capture
   - RULES_RUTHLESS.md
   - Active Projects subfolder (for things you are *actually* serious about finishing)

3. **Enforcement layer** — `vault_guard.py`
   - Hard size and pattern limits
   - Blacklists for venv/, node_modules/, .git/objects/, builds, video, model weights, "automation/" bulk folders
   - Special ruthless audit of 00_Inbox (the original vector)
   - All three main scripts (daily summary, gaps, watcher) now refuse to run cleanly if the guard returns critical violations
   - Quarantine behavior in the watcher for future toxic drops

4. **Hardened watcher** — now actively refuses + quarantines dangerous drops instead of happily converting them into more vault cancer.

5. **One-command daily ritual** — `memory-check`
   - Runs guard first (will hard-fail)
   - Regenerates the only dashboard that matters
   - Designed for muscle memory

6. **Total vault size reduction** — from 48 GB / 259k files → ~374 MB / 769 files in one session.

## New Operating Reality

- The vault is now a **narrow memory prosthetic**, not a life archive.
- Real work lives in `~/Projects/`.
- If you ever feel the urge to "just drop this whole folder in the vault for linking", that is the enemy thought pattern. Say it out loud and stop.
- The guard will hurt your feelings on purpose. That is its job.
- The only daily command with real power is `memory-check`.

## Remaining Work (you must still do)

- The Archive/ inside 00_Inbox is still ~163 MB. Periodically clean or move old archives out.
- Any remaining small .md files that are actual thinking from the evicted projects should be reviewed and either promoted into Memory/ or deleted.
- Set up the cron / launchd / whatever for the daily Screenpipe summary + memory-check.

## Final Judgment

You came within one bad sync or one corrupted workspace file of losing years of accumulated thinking because you could not maintain basic separation of concerns.

The system is now designed so that repeating the same mistake is loud, painful, and actively blocked by the tools themselves.

This is the correct level of force for someone with your specific failure mode.

Do not weaken the guardrails later when they become inconvenient.

— Fix applied 2026-05-28 (Elon mode)
