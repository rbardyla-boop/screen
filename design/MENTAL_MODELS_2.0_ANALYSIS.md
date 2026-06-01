# Mental Models Analysis — Second Brain 2.0 (the "cutting-edge upgrade")

**Date:** 2026-06-01
**Why this doc exists:** `design/SCOPED_VISION.md` locks scope and states: *"Any expansion requires running a new Pre-Mortem + Inversion first."* The user asked to build "the most cutting-edge second brain — the 2.0 version." That is an expansion. This is the mandatory pre-mortem before any code. It was run alongside a 5-advisor LLM Council (see `council-report-2026-06-01-1804.html`).

---

## PRE-MORTEM (Primary — "about to start a big project")

**It is 6 months from now (Dec 2026). The "2.0 second brain" is dead or has become another abandoned, anxiety-inducing folder.** How did it happen?

1. **The recursion trap.** The user has a failure mode: *start ambitious things → forget them.* 2.0 was itself an ambitious thing. We built a sprawling "cutting-edge" platform (semantic search + knowledge graph + local LLM + agentic capture + causal modeling), it was never finished, and it became the largest open loop in the system — the tool meant to fight abandonment, abandoned.
2. **Bloat recurrence.** 2.0 introduced a vector DB / embedding store / new index that grew unbounded. The guard didn't cover it. Six weeks later the "second brain" was slow and scary again.
3. **Capability without behavior change.** We added impressive retrieval and synthesis, but the user still never *looked* — because the system still waited to be pulled. Beautiful outputs nobody read.
4. **Rust quicksand.** We started the `memcore` rewrite. Months in, the daily Python tool was neglected, the Rust tool wasn't usable yet, and the user had neither.
5. **Confident-wrong erosion of trust.** An "ask my life" RAG/LLM layer gave plausible-but-wrong answers about the user's own past. They stopped trusting the system and quietly dropped it.

**Blindspot audit — what would the user rate "low probability" but is actually highest risk?**
- The recursion trap (#1) and bloat recurrence (#2). The user believes "this time I'll be disciplined / it's a real upgrade." That belief is exactly the 2026-05-28 precondition.

**Pre-actions (must be true in the architecture from line 1):**
- 2.0 must be *subtractive in spirit*: the increment must be small enough to finish in one sitting and immediately usable.
- No new unbounded data store. Reuse existing Markdown + `.loop-state.json`. Any new file is single and overwritten (never grows).
- The increment must change **behavior**, not just capability: it must push to the user without being asked.
- Stay in Python. The Rust `memcore` stays locked.
- Gate on `vault_guard`; degrade safely; refuse on critical violations.

---

## INVERSION (How do we *guarantee* 2.0 also fails like the 48GB disaster?)

Every reliable way to fail:
- Optimize for "looks cutting-edge" before changing whether the user acts on their loops.
- Add a vector index / embedding cache / model cache with no size policy and no guard coverage.
- Make the new feature something the user must remember to invoke.
- Begin the Rust rewrite "because it's the real architecture."
- Ship an LLM Q&A layer that answers confidently and wrongly about the user's life, with no provenance.
- Add five features instead of finishing one.

**Inverted into design rules (visible in code + docs):**
- One increment, finishable now, usable today.
- Zero new growable storage. Single overwritten output file.
- Delivery is **push** (notification + timer), not pull.
- Deterministic core (no model in the critical path); AI phrasing optional and clearly non-authoritative.
- Guard runs first, always.
- The Rust engine and the ML "abandonment fingerprint" are explicitly out of scope for 2.0.

---

## FIRST PRINCIPLES (strip the framing)

The user is not trying to "own a cutting-edge second brain." They are trying to **outsource the one executive function their brain fails at: closing loops they started.** The undeniable atoms:
- The data is already captured (screen/audio → Screenpipe), and gaps are already detected (`vault_intelligence.py gaps` + `.loop-state.json` age tracking).
- The 48GB event proved more *data/capability* is not the constraint; *signal reaching behavior* is.
- The highest-leverage unit of value is: *"these specific things are dying; here is the one next step for each — and you didn't have to ask."*

Rebuilt from atoms: a tiny, deterministic, **proactive** daily brief of the stalest open loops, delivered as an ambient interrupt, gated by the guard. Everything else is deferred.

---

## REGRET MINIMIZATION (80-year-old test)

Low regret: a narrow, proactive prosthetic that, for years, quietly made sure abandoned threads resurfaced before they died — and that *stayed small and trustworthy*. High regret: another ambitious "platform" that ate months and became vaporware, or a second bloat corpse. The 80-year-old already knows: **ship the smallest thing that changes behavior; defer the seductive engine until the small thing has earned daily trust.**

---

## SYNTHESIS — The only acceptable 2.0

> **Memory Core 2.0 = "the second brain that reaches OUT to you."**
> Not more capability. The *delivery* of existing signal, made proactive and impossible to ignore.

**In scope (v2.0, this increment):**
- `vault_brief.py`: rank live open loops by **staleness** (from `.loop-state.json`), take the top 3, attach a one-line next action, render a Morning Brief.
- A `Notifier`: stdout + desktop `notify-send` + optional env-gated `ntfy` phone push.
- Write a single overwritten `Memory/Morning-Brief.md` (anti-bloat).
- Guard-gated; safe-degrading.
- Opt-in `--install-timer`: generate a systemd user timer so it fires every morning automatically.

**Explicitly out of scope (deferred behind a future pre-mortem):**
- The Rust `memcore` rewrite.
- Causal "abandonment fingerprint" / temporal ML modeling.
- Vector/semantic search, RAG "ask my life" Q&A, knowledge-graph visualization, local-LLM-in-critical-path.

**Success criteria:** Within a week of real use, the user reports a stale loop resurfaced and was acted on *without them remembering to run anything*. The Memory/ surface stays small and fast. No new bloat vector exists.

This is the only 2.0 design that survives the pre-mortem.
