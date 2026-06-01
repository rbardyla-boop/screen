# Project Charter — Screenpipe → Obsidian Second Brain

Source of truth for significant architectural decisions (per `.claude/rules/engineering.md`).

## What this system is

A personal memory prosthetic for one validated failure mode: **"I start ambitious things and then forget they exist."** It captures the user's screen + audio 24/7 via Screenpipe and maintains a small, sacred Obsidian `Memory/` core. After the 2026-05-28 48GB bloat near-death, the entire system is governed by **ruthless anti-bloat** (`vault_guard.py`, ~50-note `Memory/` cap, one daily `memory-check` ritual).

## Invariants (do not weaken)

- **Source of truth = plain Markdown + `.loop-state.json`.** Any index/store must be rebuildable and size-bounded.
- **The guard runs first** on the daily path and may force "degraded but safe" mode.
- **No unbounded new storage.** New outputs are single, overwritten files, not append-forever logs.
- **Smallest coherent change** that completes the user path (see `.claude/rules/engineering.md`).

---

## ADR-001 — 2026-06-01 — Second Brain "2.0" is delivery, not capability

**Status:** Accepted. **Method:** LLM Council (5 advisors + 5 anonymized peer reviewers) + mandatory Pre-Mortem/Inversion (`design/MENTAL_MODELS_2.0_ANALYSIS.md`, `council-report-2026-06-01-1804.html`).

**Context.** The user requested "the most cutting-edge second brain — the 2.0 version." This is an expansion, which `design/SCOPED_VISION.md` gates behind a fresh pre-mortem. Two failure modes were weighed: (1) data bloat; (2) the user abandons ambitious *tools* — so a sprawling 2.0 is the likeliest way to recreate failure. Code review of the current system confirmed: the gaps engine + `.loop-state.json` already detect and age open loops, but there is **zero** proactive delivery — `memory-check` is pull-only.

**Decision.**
- 2.0 = **proactive delivery of existing signal**, branded *"the second brain that reaches OUT to you."* Build a deterministic **Morning Brief** that surfaces the 3 stalest open loops (age + one next action) and pushes it (desktop + optional phone) on an automatic timer, gated by the guard, into a single overwritten file.
- **Stay in Python.** The Rust `memcore` vision (`design/SCOPED_VISION.md`) **remains locked and unbuilt.**
- **Deferred behind a future pre-mortem:** causal/temporal ML "abandonment fingerprint", vector/semantic search, RAG "ask my life" Q&A, knowledge-graph visualization, local-LLM-in-critical-path.

**Consequences.**
- New module `vault_brief.py` + tests; reuses `collect_gaps`, `.loop-state.json`, `vault_guard.run_audit`, `ai_provider` (AI optional, never authoritative).
- Delivery via a `Notifier` (stdout + `notify-send` + env-gated `ntfy`); opt-in `--install-timer` generates a systemd user timer.
- Anti-bloat preserved: no growable store; `Memory/Morning-Brief.md` is overwritten daily.

**Salvaged from the dissent.** The Expansionist's causal engine was rejected as the "seductive path to another abandoned tool," but its one zero-ML, high-signal sliver — **ranking by staleness (time-since-touch)** — is adopted as the brief's ordering. It is a "this loop is about to die" signal computed from data that already exists.

**Also recorded:** the uncommitted `vault_guard.py` change (exempting `.claude/` tool-config trees from the directory-*name* toxic check while keeping size/extension/total checks) is a sound narrowing and should be committed so the guard stops drifting.
