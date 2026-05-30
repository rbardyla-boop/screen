# Mental Models Analysis — Building a Rust Parallel Second Brain

**Date:** 2026-05-28
**Context:** User wants a full Rust version of Obsidian in parallel, with superior automatic document-to-Markdown conversion (scheduled or on-demand), that is fast/strong/no errors, and functions as a better second brain — specifically for memory of unfinished tasks.

This document applies the mental-models.skill frameworks ruthlessly before any code is written.

---

## MODEL DEPLOYED: PRE-MORTEM (Primary — "about to start a big project")

**It is 6 months from now (Nov 2026). This Rust "Obsidian" project is dead or has become another abandoned folder that makes the user feel worse.**

**Failure scenarios (specific, scenario-level):**

1. **Scope explosion death**
   - We tried to replicate too many Obsidian features (graph view with nice rendering, block references, plugins system, WYSIWYG) in the first 4 months.
   - The core ingestion pipeline and Unfinished Work engine were never made production-grade.
   - Result: A pretty but unreliable TUI that the user opens once, sees it's incomplete compared to Obsidian, and never uses again.

2. **Bloat recurrence (the exact same failure mode)**
   - The new Rust tool had weak or no guardrails in the watcher/ingestion layer.
   - User (in a moment of "this project is important") dropped several large codebases + media folders "just for a week" into the watched directory.
   - Tantivy index blew up, search became slow, the "second brain" once again became the thing that makes the user anxious instead of helping.
   - The tool had no equivalent of the `vault_guard` that actively refused and quarantined.

3. **Scheduling / reliability failure**
   - The "off hours" processing never worked reliably across reboots/sleep.
   - User had to manually trigger conversions, defeating the "automatic on off hours or immediately on ask" requirement.
   - OCR jobs hung or crashed silently on certain PDFs.

4. **No migration / coexistence story**
   - The tool couldn't safely live alongside the existing Obsidian vault + Python scripts.
   - User was forced to choose: use broken Obsidian or switch to half-finished Rust thing.
   - Chose neither consistently.

5. **Performance cliff at real data volume**
   - Even with Rust + Tantivy, once the user put their actual writing volume in, the "fast" claims didn't hold because we indexed every token without smart scoping (Memory core vs archive vs active).

6. **The tool itself became the new open loop**
   - Building this became another ambitious project the user started and didn't finish, adding to the very "unfinished work" burden the tool was supposed to solve.

**Blindspot audit:** Which of these would the user currently rate as "low probability"?
- #2 (bloat recurrence) — "I'll be more disciplined this time because it's Rust."
- #1 (scope creep) — "We'll keep it minimal."

These are the highest risk.

**Pre-actions (what must be true in the architecture from week 1):**
- Ruthless scope lock: Ingestion + Gaps Engine + Scheduling + Fast local search + simple daily TUI/CLI are the *only* things in v0.1. No graph rendering, no plugins, no block refs.
- The guard/quarantine logic must be deeper and stricter than the Python version — it is a core architectural invariant, not a script you run sometimes.
- Every watched directory must have an explicit "type" (SacredMemory, ActiveProject, Archive, Inbox) with different policies.
- Scheduling must be implemented as a real, restart-safe daemon from the beginning (systemd user service or self-contained).
- The project must be usable *in parallel* with existing Obsidian on day 1 (read-only mode on the same vault at minimum).
- Every major component must have a "how this prevents the 2026-05-28 disaster" test or invariant in the code/docs.

---

## MODEL DEPLOYED: FIRST PRINCIPLES

**What are you actually trying to achieve? (strip framing)**

A personal knowledge + memory system that:
- Automatically and reliably turns incoming documents (PDFs, Word, images with text, etc.) into clean, searchable, linkable Markdown with rich metadata.
- Does the heavy lifting on a schedule (off-hours) or instantly when asked, without errors or manual babysitting.
- Has an always-on, high-signal "unfinished work / open loops" memory surface that surfaces what you started and didn't finish better than any current tool.
- Remains fast and pleasant to use even after years of real usage and real data volume.
- Does not require the user to be a perfect digital minimalist to avoid death-by-bloat.

**Undeniably true atoms:**
- Local plain Markdown files (with frontmatter) are the correct source of truth for longevity and portability.
- The user's specific cognitive failure mode (start → evaporate) is the highest-leverage thing to optimize for — more than pretty UI or every possible Obsidian feature.
- Ingestion quality + reliability + guardrails is 80% of the value for this user. The rest is retrieval + surfacing of open loops.
- Any system that allows "just drop this giant folder here temporarily" will eventually be abused by this user and die the same death.
- Python + external tools (pandoc, tesseract) has fragility, slow startup, and poor parallelism. Rust + native or well-bound crates can be dramatically better on speed + error handling + one binary.
- Scheduling + background processing that "just works" is a first-class feature, not an afterthought.

**Assumptions being challenged:**
- "We need to clone Obsidian's UI/features to be better" → False. Obsidian's UI is fine. Its lack of guardrails and weak automation for *this user's actual problem* is the issue.
- "A general-purpose note app will naturally support strong unfinished-work memory" → False. It requires deliberate, first-class design (the Python gaps tool was a good start but too weak and not enforced).
- "Rust will automatically make it fast and reliable" → False. Bad architecture in Rust is still bad. We must design the anti-bloat invariants into the data model and ingestion layer.

**Rebuilt solution from the atoms:**
- A Rust binary (`memcore` or `mindforge` or `loopcore`) that is both CLI and long-running daemon.
- Strict directory typing with policy engine.
- World-class parallel ingestion engine (notify + rayon/tokio + pdfium or pdftotext bindings or pure Rust where possible + tesseract via leptess or similar).
- Native "Gaps Engine" that is fast, incremental, and has review workflow UI.
- Tantivy for search (far better than ripgrep + simple scans).
- Simple but excellent TUI (ratatui) or minimal local web UI (axum + htmx or leptos) for the daily memory surface.
- Built-in scheduling (or excellent systemd integration + self-contained cron).
- The guard is not a script — it is the ingestion layer and the query layer refusing to operate on diseased state.

---

## MODEL DEPLOYED: INVERSION (How do we guarantee this also fails like Obsidian did?)

**Every way this Rust project guarantees the user ends up with another slow, anxiety-inducing, abandoned second brain:**

- We optimize for "looks like a real app" before the ingestion pipeline is boringly reliable.
- We allow a single "watched" root without strict sub-policies (Sacred vs Everything Else).
- We make the guard optional or "you can turn it off for big imports".
- We build the pretty graph view in month 2 instead of making `memory-check` (or equivalent) the single most reliable command in the user's life.
- We use heavy dependencies that pull in the world (full webview, complex UI framework) before the core is solid.
- We don't implement quarantine + automatic "this folder is now read-only until you clean it" behavior.
- We treat scheduling as "nice to have later" (user will have to remember to run things manually → it dies).
- The project becomes yet another open loop because we aimed too high in v1.

**Inverted into concrete design rules (these must be visible in the architecture doc and code):**
- v0.1 ships *only* when the ingestion is more reliable than the Python version + the Gaps engine is better + scheduling works.
- Every watched path must declare its "class" (MemoryCore, Inbox, Active, ColdArchive). Different classes have different max sizes, allowed file types, and processing priority.
- The guard runs on every ingestion event and before every search/gaps operation. It can put the whole system into "degraded but safe" mode.
- No UI work (beyond excellent CLI + one simple TUI screen for the daily dashboard) until the above is true and has been used daily for weeks by the actual user.
- The default is to refuse large or toxic drops with clear, actionable error + auto-quarantine. "Temporarily disable" does not exist in the first version.

---

## MODEL DEPLOYED: REGRET MINIMIZATION (80-year-old version)

**80-year-old you, looking back at the decision to build (or not build) this in 2026:**

The version where you built a narrow, ruthless, purpose-built Rust engine for ingestion + open-loop memory that actually stayed fast and useful for the next 20 years → low regret.

The version where you either:
- Did nothing and kept suffering with the 48GB Obsidian corpse, or
- Started another ambitious "full Obsidian in Rust" that became vaporware or another bloated thing

...both feel like the kind of thing that would haunt you.

**The 80-year-old version already knows:** Build the smallest possible thing that solves the actual recurring failure mode (unreliable ingestion + no persistent memory of unfinished work) with extreme prejudice against scope and bloat. Make it so good at that narrow job that it earns the right to grow later.

---

## SYNTHESIS — THE ONLY ACCEPTABLE APPROACH

From the models:

We are **not** building "a full Rust Obsidian".

We are building **a superior, narrow, bloat-proof second brain engine in Rust** whose primary jobs are:
1. Never let the user accidentally (or "temporarily") destroy the performance and signal of their memory system again.
2. Make document → clean Markdown conversion automatic, parallel, reliable, and scheduled.
3. Make the "what did I start and never finish" surface the best and most used part of the entire system.

Everything else (beautiful graph, block references, 200 plugins) is explicitly out of scope for v1 and will only be considered after the above three things are boringly excellent and the user has been using it daily for real work without it becoming the next tar pit.

This is the only design that has a chance of not failing the Pre-Mortem.

Next step: Write the narrow, ruthless Product Requirements / Architecture doc using this analysis, then execute with TDD.
