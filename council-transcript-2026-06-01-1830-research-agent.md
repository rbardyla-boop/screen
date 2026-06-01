# LLM Council Transcript — Autonomous Clipping-Research Agent (Pre-Mortem)

**Timestamp:** 2026-06-01 18:30
**Why:** The 2.0 verdict (ADR-001) deferred autonomous research behind a fresh pre-mortem. The user asked: "can we make the brain investigate/research the topics in my clippings over time in off-hours… do something with the articles/resources that just sit there — sometimes they might connect to something?" This is that pre-mortem, run as a 5-advisor council + anonymized peer review.

## Framed question

Should the second brain autonomously research/enrich the topics in the user's saved clippings (~62 Literature + 27 Permanent notes) over time in off-hours? In what bounded form? (a) external web fetch vs only deepening/connecting what's already saved; (b) where fetched content lives — sacred Memory/ vs a capped airlock; (c) local model vs cloud for an unattended nightly loop; (d) how it avoids becoming another abandoned/bloated subsystem; (e) the highest-leverage bounded first version. Hard history: a 48GB/259k-file bloat near-death (external content is the bloat vector); the user also abandons ambitious tools; a free local model (ollama gemma3:12b) + a forward-only `connections` engine + a nightly operator already exist.

## Anonymization map (revealed)
A = First Principles · B = Executor · C = Outsider · D = Expansionist · E = Contrarian

## Advisor responses

**The Contrarian (E):** The desire is a displacement behavior — fetching new info instead of processing what you have. 48GB was a *processing-debt* problem, not storage; autonomous research adds debt faster than you clear it, the output goes unread → corpse. Local models on research tasks produce confident nonsense → ghost citations corrupt your own memory. "Serendipitous resurfacing" already half-exists in the connections engine and isn't maxed. The version that earns its right is NOT research: a weekly digest of which Literature notes have ZERO connections after 30 days. Force the bottleneck into view; make the human process before the machine generates.

**The First Principles Thinker (A):** The user doesn't want research — they want to stop feeling guilty about saved things. Every clipping is a broken promise ("I'll come back to this"); research generates MORE content around the broken promise. Reframe: not "research this topic?" but *"is this clipping still load-bearing?"* First version: zero external fetch, zero new content; one weekly local-model call per clipping comparing its core claim against Open-Loops + recent notes → a verdict (still relevant / resolved / orphaned) as a single tag mutation + one sentence. No new notes. "How do we close the loop on why they were saved?"

**The Expansionist (D):** The undervalued upside: this quietly assembles your *intellectual autobiography* — a latent book (or three). Every clipping was a vote; cross-pollinated nightly by the free local model, they reveal chapter structures you never consciously assembled. "Synthesis-as-first-draft": wake to a 400-word synthesis of three notes that suddenly cohere. Compounding personal insight; the corpus is irreproducible = the moat. The longer it runs, the more unfair the advantage.

**The Outsider (C):** 89 unread articles = a filing habit, not a learning habit. An AI that reads them and sends nightly reports is just a 90th thing you won't read. What happens when two articles "connect"? You feel briefly interested, file it, nothing changes. The night-research idea solves for the *feeling* of being on top of material, not using it. Real fix: friction on INPUT, not more output — delete one to save one; or force one article/week to the top of the screen, write one sentence before you can dismiss it. Ask why you save things you don't read.

**The Executor (B):** Fastest path: add `run_resurface()` to `vault_ai.py` modeled on the existing `run_connections()`, but sort notes by oldest mtime (most dormant), take the bottom ~20, ask the local model which dormant notes connect to recently-touched ones. Use ollama gemma3:12b only (free, 128k ctx, no runaway-cost risk; a cloud model in an unattended cron at $0.05/run is dangerous). Skip external web fetch entirely — you have 89 notes you've never connected; that IS the research. Wire into the existing nightly operator (no new cron). ~40-line diff. Resurface first; internet later.

## Peer reviews (5 independent, anonymized)

- **Strongest: B (4/5)** — the only response that converts the decision into a concrete, bounded, infrastructure-reusing action with hard scope limits. One reviewer chose **E** for the "earn-its-right" zero-connection gate that adds nothing to the pile.
- **Biggest blind spot: D (5/5, unanimous)** — "mistakes a hope for a design; no stopping condition, no success definition, no mechanism to prevent the 48GB death; the exact rationalization that produced the prior bloat; the most seductive path back to 48GB."
- **What ALL advisors missed (emergent):**
  1. **Nobody verified the user reads the EXISTING autonomous output.** The connections engine + nightly operator already produce reports (Connections-*.md). If those already go unread, any new loop "compounds the ignored-output problem." Audit whether current output changes behavior *before* authorizing a new loop.
  2. **Write enrichment in-place on the original note, not as new files.** "The real failure mode isn't bloat or bad models — it's that the second brain becomes write-only." In-place keeps corpus size flat and makes enrichment discoverable at point-of-need, eliminating the "90th unread thing."
  3. **The capture/save gesture is a candidate higher-leverage intervention** than the nightly cron (filter at input, not after).

## Chairman's Verdict

**Where the council agrees:** No external web fetch — 4/5 advisors and every reviewer reject it as the literal bloat vector. Local model only (free; no unattended-cron cost runaway). The problem is *processing debt / write-only accumulation*, not a lack of research. Do not generate a new pile of reports nobody reads.

**Where it clashes:** The Expansionist's "autonomous synthesis / latent book" vs everyone — resolved decisively against (unanimous blind-spot: it's the rationalization that rebuilds the tar pit). Secondary clash — Executor's `Resurface-DATE.md` report vs First Principles/Contrarian/Outsider's "no new output." Resolved by reviewer #4's insight: **keep the Executor's mechanism, change the output** — write the connection in-place on the dormant note + ride the ONE best hit on the delivery channel we already proved reaches the user.

**Blind spots caught:** must verify the existing pipeline is read before adding a loop; write in-place not new files; capture-side friction is a separate lever.

**The recommendation:** Do **not** build a research agent. Build the **Off-Hours Librarian** as a tightly-bounded extension that sidesteps the unread-report trap: a nightly, local-model-only pass that reverses the `connections` mtime filter to find the single strongest link between a *dormant* clipping and the user's *active* work, writes a one-line verdict **in-place** on the dormant note (`> 🔗 resurfaced DATE: connects to [[active]] — relevant? / looks resolved / orphaned`), and feeds the ONE best resurfacing into the **Morning Brief that already pushes to the phone**. No external fetch. No new report files. No cloud. Guard-gated. Corpus size stays flat. It reuses `run_connections` + the delivery channel already built — not a new subsystem.

**The one thing to do first:** Prove the channel before building the engine. Add the single best "dormant clipping that connects to today's work" line to the existing Morning Brief, generated nightly by the local model. If within 2–3 weeks the user acts on even one resurfaced clipping, expand. If not, the "do something with my clippings" desire was about guilt (First Principles/Outsider) — and the real answer is capture-side friction, not a research engine.
