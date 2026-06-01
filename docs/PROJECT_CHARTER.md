# PROJECT CHARTER — Screenpipe-to-Obsidian / memcore

**Status:** Active. This is the source of truth for scope, invariants, and major architectural decisions.

**Last Updated:** 2026-06 (plan mode session 019e8284-8aab-7861-92ff-55df1a9a397a)

## Core Purpose
Build and maintain the highest-leverage personal memory prosthetic for a user whose primary cognitive failure mode is "start ambitious projects / research threads and then completely forget they exist."

The system must remain **small, fast, high-signal, and ruthlessly anti-bloat** for 10+ years.

## Locked Strategic Direction (Post 2026-05-28 Incident)
See [design/SCOPED_VISION.md](design/SCOPED_VISION.md) and [design/MENTAL_MODELS_ANALYSIS.md](design/MENTAL_MODELS_ANALYSIS.md).

- Primary deliverable: `memcore` (Rust CLI + daemon) focused on:
  - Automatic, safe, reliable document ingestion (PDF/DOCX/images/OCR → clean frontmatter-rich Markdown).
  - First-class "Unfinished Work / Open Loops / Gaps" engine (superior to current Python `vault_intelligence.py`).
  - Strict directory-class policies + guardrails that actively prevent bloat (MemoryCore sacred, Inbox temporary + capped, Active limited, Cold/Archive deprioritized).
  - Fast local search (Tantivy) + simple backlinks.
  - Scheduling for off-hours processing.
  - Minimal TUI/CLI for daily review.
- Must coexist with existing Obsidian vault + current Python toolchain on day 1.
- Explicitly out-of-scope for v0.1/v0.2 without new Pre-Mortem: graph visualization, plugins, WYSIWYG, full Obsidian parity, cloud, mobile, bulk data ingestion of any kind.

**Every decision must pass the test: "Would this have prevented or survived the 2026-05-28 48 GB disaster?"**

## Architectural Decision Records

### ADR-001: Literature Discovery / "One Brain" / Analogical Leap Capability (2026-06)
**Decision:** The full "Caitlin One-Brain" scientific literature discovery engine (multi-agent swarm for on-demand analogical transfer, distant-domain recombination, contradiction/gap hunting, and bold hypothesis generation across open corpora) **will be developed as a completely separate project and repository**.

**Rationale (Caitlin/Weinstein lens applied to architecture):**
- The pattern in the vision and in this project's own DNA (`.claude/claude.md` Core Directive, `truth_seeker/`, `llm-council/`, existing `vault_ai.py` contradict/synthesize/gaps, "Swarm Colony") is that breakthroughs come from *forced cross-silo recombination from minimal high-signal clues*, not from owning more data locally.
- This repo's sacred invariant (post-mortem) is anti-bloat + narrow personal memory surface. Bulk or even moderate literature ingestion would recreate the exact 48 GB failure mode at larger scale.
- Semantic Scholar Academic Graph API (with SPECTER2 embeddings served for free, citation graph, fieldsOfStudy, TLDRs) + arXiv (on-demand only) already provide 80-90% of the required external structure without any local bulk storage or gray-zone sources.
- The personal vault (Memory/Literature/, Unfinished Work Dashboard, daily synthesis from Screenpipe) is the *perfect* "minimal structured clues + noisy personal context" layer. The external brain should consume it read-only as seeds, never the reverse.

**Consequences:**
- This repo owns: personal capture (Screenpipe), ingestion hardening (memcore), gaps/unfinished-work engine, guardrails, clean note production, and high-signal export surfaces.
- The new "Caitlin Brain" (or serendipity-engine / analogical-leap) repo will own: on-demand S2/arXiv Scout, Pattern Finder (distant analogies via SPECTER proximity + field jumps), council-style Generator + ruthless Critic/Validator (reusing or vendoring patterns from this repo's `.claude/`), tiny traceable hypothesis output.
- Bridge contract: `vault_export.py` (already exists: serializes Memory/ to portable tar.gz) + future optional `--research-seed` or `caitlin-seed-export` mode that produces minimal structured context packs (top literature notes + gaps + synthesis summaries). These packs are the standard input format for the external brain. The brain never writes back into a user's primary vault unless the user explicitly promotes a direction.
- Reusable assets from this repo (with clear notes/license): `.claude/truth_seeker/`, `.claude/skills/llm-council/`, `.claude/rules/research-evidence.md`, mental-models skill, and the overall Caitlin directive + pre-mortem discipline. These can be vendored or referenced by the new brain as its "agent personality and review kit."
- No code, dependencies, or scope from the discovery engine will enter this tree without a fresh Pre-Mortem + explicit scope expansion vote.

**Pre-Mortem conducted:** Yes (embedded in the full plan for the separate project; see session plan.md). Top risks (scope explosion, bloat recurrence, ToS/rate-limit cliff, novelty theater, evaluation death, creating one more open loop) have explicit mitigations (ruthless v0.1 lock to on-demand S2 + small retrieved sets + council critic + provenance + user feedback loop; guard philosophy ported; first 5 hypotheses manually validated).

**Status:** Approved by user in plan mode. Implementation of the *separate* brain is out of scope for this repo. Phase 0 work in this repo is limited to recording this decision and lightweight reusability tagging.

**See also:** Full plan in the originating session (`plan.md`), user vision query, Semantic Scholar API facts (rate limits, `embedding.specterv2`, fields), and the locked SCOPED_VISION.md.

---

## Invariants (Non-Negotiable)
- Source of truth = plain Markdown files + frontmatter (index is disposable).
- The tool must be able to say "No" to the user and be right (guard, quarantine, size caps, scope lock).
- Memory/ core must stay tiny and fast (<150 MB target, high signal only).
- All external data (including future literature seeds) treated as untrusted; validate at boundaries.
- Research-evidence discipline: separate observation / inference / speculation; define success criteria; label uncertainty; identify falsifiers for architectural claims.
- Security-first: no hardcoded secrets; least privilege; fail closed on sensitive writes (see hooks/guard-sensitive-write.py).

## Current State (as of last LLM Context Brief + plan session)
- Python toolchain (Screenpipe integration, vault_ai / vault_intelligence / guard / night_operator / skills / graph / export) is the active production surface.
- Rust memcore path is the locked hardening/evolution target for ingestion + gaps.
- .claude/ contains the full ECC agentic framework (council, mental models, truth seeker, plan/review/verify/build/ship skills, rules) that both enforces discipline here and serves as reusable kit for related high-ambition projects.

## How to Propose Change
1. Run a new Pre-Mortem + Inversion (mental-models skill) for any scope-expanding idea.
2. Update this charter with a new ADR section (date, decision, rationale, consequences, falsifiers).
3. Update SCOPED_VISION.md if the locked v0.1 surface changes.
4. Tag affected skills/rules with reusability notes when they become assets for external work.

This charter is the single place that prevents the project from quietly becoming the thing it was built to escape.