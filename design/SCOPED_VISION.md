# SCOPED VISION — memcore (Rust Second Brain Engine)

**Status:** Locked. Do not expand without explicit re-authorization after Pre-Mortem review.

**Derived from:** Mental Models Analysis (2026-05-28)

## The Actual Goal (First Principles)

Build the smallest possible, highest-leverage Rust tool that makes the following true for this user for the next 10+ years:

1. **Ingestion is automatic, fast, reliable, and safe.**
   - Any document dropped into the right place gets turned into clean, frontmatter-rich Markdown.
   - Happens in the background (off-hours) or instantly on demand.
   - Errors are impossible to miss and never corrupt the vault.
   - Toxic / oversized / dev-workspace drops are refused and quarantined by default.

2. **The "unfinished work / open loops" memory surface is the best part of the system.**
   - First-class, fast, reviewable "Unfinished Work Dashboard" that actually surfaces tasks the user started and abandoned.
   - Better heuristics + persistence + workflow than the Python `vault_intelligence.py gaps`.
   - Integrated with daily Screenpipe summaries.

3. **The system stays fast and high-signal forever.**
   - Anti-bloat is an architectural invariant, not a nice-to-have script.
   - The tool actively protects the user from their own past failure mode.

It must coexist with the existing Obsidian vault on day 1 (can read the same Markdown files, can run in parallel).

It does **not** need to be a full note editor, full graph visualizer, or plugin host in v1.

## Explicit In-Scope for v0.1 (MVP that earns the right to exist)

- **Binary:** `memcore` (one binary: CLI + daemon capability)
- **Core commands:**
  - `memcore watch` / daemon mode (background ingestion)
  - `memcore ingest <path>` (on-demand, immediate)
  - `memcore gaps` (or `memcore review`) — the superior Unfinished Work engine
  - `memcore search <query>`
  - `memcore schedule` (configure off-hours jobs)
  - `memcore guard` (explicit audit + repair)

- **Ingestion pipeline (the hard part, must be excellent):**
  - Uses `notify` crate for real-time watching (better than Python watchdog)
  - Parallel processing (tokio + rayon where appropriate)
  - Support for: PDF (pdfium-render or poppler via ffi, or pdftotext), DOCX/ODT/RTF (via pandoc or native), images (tesseract via leptess or ocrs), plain text
  - High-quality frontmatter enrichment (source, date ingested, content hash, OCR confidence, etc.)
  - Strict quarantine directory + never-mutate-originals policy
  - Built-in equivalent of the Python vault_guard, but deeper (directory class policies, size caps per class, toxic pattern detection at write time)

- **Directory class system (the anti-bloat core):**
  Every watched root or subfolder declares a class:
  - `MemoryCore` (sacred, tiny, always fast, highest priority for gaps)
  - `Inbox` (temporary, strict size + type limits, auto-archive after processing)
  - `Active` (current serious projects — limited bloat allowed)
  - `Cold` / `Archive` (heavy stuff, lower priority indexing or excluded from gaps/search by default)

  The engine refuses to operate normally if these policies are violated.

- **Gaps / Unfinished Work Engine:**
  - Incremental (only re-scan changed files since last run)
  - Much better signal than regex + LLM dump (hybrid: strong markers + embedding similarity for "this feels like an abandoned thread")
  - Persistent state (SQLite or sled) for "I've reviewed this", "killed on date", "next action date"
  - Workflow: `memcore review` shows the dashboard + lets you act on items in one session
  - Integration hook for daily Screenpipe summary to feed new potential loops

- **Search:**
  - Tantivy full-text index (fast, local, typed by directory class)
  - Simple backlink resolution (file-based, like Obsidian)
  - Fast enough that `memcore search "open loop"` feels instant even on large vaults

- **Scheduling:**
  - Either excellent built-in scheduler (tokio + cron-like) or first-class systemd user service + timer unit generation
  - "Off hours" (e.g. 2-5am) heavy jobs + "immediate on ask" path
  - Resilient to machine sleep/reboot

- **TUI / Daily Surface (minimal but excellent):**
  - One ratatui screen for the daily review (Unfinished Work + recent ingestions + quick actions)
  - Everything else is excellent CLI (the user lives in terminal anyway)

- **Guardrails & Philosophy (non-negotiable invariants):**
  - The tool must be able to say "No" to the user and be right.
  - Source of truth is always plain .md files + sidecar .meta.json or frontmatter. Index can be rebuilt.
  - One binary, minimal dependencies where possible, cross-platform (Linux first, as this is the user's OS).
  - Every error path is loud and comes with the exact command to fix the state.

## Explicit Out-of-Scope for v0.1 (and probably v0.2)

- Graph visualization / pretty interactive graph
- Block-level references or transclusion
- WYSIWYG / rich text editing
- Plugin system
- Mobile app
- Cloud sync (local first, user can use Syncthing/git/etc. on the .md files)
- Full Obsidian feature parity
- Beautiful web UI (minimal local web for review is acceptable later if TUI is insufficient)

These things can be added only after the three primary goals above are boringly solid and the user has real daily usage data showing the system is not repeating the 48GB disaster.

## Success Criteria (how we know we didn't waste time)

- User can drop a PDF into the Inbox at 11pm and find the clean Markdown + extracted open loops in the review the next morning without touching anything.
- `memcore review` becomes the single most used "second brain" command (replaces most Obsidian daily usage for memory purposes).
- After 3 months of real use, the vault + indexes are still fast.
- When the user tries to abuse it the old way (dumping a 5GB project folder), the system actively stops them and explains why, instead of silently dying 6 weeks later.

## Name

Primary binary + project: **memcore**

(Alternative considerations that were rejected for being too cute or too vague: mindforge, loopcore, aegis, recall, unspool, echo)

`memcore` communicates exactly what it is: the core memory engine.

---

**This scope is locked by the mental models analysis. Any expansion requires running a new Pre-Mortem + Inversion first.**

## Immediate Next Actions (TDD order)

1. Cargo workspace + binary skeleton with strict linting + error handling posture.
2. Directory class + policy engine (the foundation of anti-bloat).
3. Guard / audit implementation (port + improve the Python logic).
4. Basic watcher + one high-quality converter (start with PDF via a good Rust path).
5. Tantivy index skeleton + simple search.
6. Gaps engine v1 (markers + simple persistence).
7. CLI structure + daemonization.
8. Scheduling.
9. TUI daily review surface.
10. Integration tests + real-user dogfooding loop with the existing vault.

All of the above must pass the "would this have prevented or survived the 2026-05-28 48GB incident?" test.
