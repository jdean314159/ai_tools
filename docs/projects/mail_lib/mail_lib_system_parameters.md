# mail_lib — System Parameters & Roadmap

**Status:** Architecture/parameters note. Captures decisions made while scoping the full system, after
v0's live run. Not a build spec — the source of truth for *what we're building and why* before each
sprint gets its own thin spec.
**Current implementation state:** see `mail_lib_status_v0.1.md`.

---

## The system in one line

A local-first, privacy-bounded email tool that triages mail, learns the maintainer's priorities and
voice from how they react, and becomes a conversational memory of their correspondence — built so each
capability forces a concrete improvement in the `ai_tools` libraries.

## Primary motivation (keeps the project honest)

The maintainer spends significant time daily on email: dropping low-interest mail and reading what
matters (AI news, personal interest). The first-order goal is **doing this faster**. That payoff lands
mostly in sprints 1–2 (rules + summaries), NOT the deep learning loop — useful to remember when
sequencing against actual pain rather than architectural elegance.

## Architecture (dependency order; each sprint is usable alone and enables the next)

1. **Deterministic personal-rule engine** — maintainer declares what matters (sender/domain allowlist,
   subject/topic rules), each with a target priority; personal rules **win over** built-in heuristics.
   Model-free. Fixes buried preferred notifications, publications, and personal-interest event mail
   now, and becomes the surface the maintainer reacts to and corrects. **This is the foundation;
   build first.**
2. **Behavioral instrumentation** — capture star/read/reply/ignore actions into `engram` as labeled
   observations. The data substrate the learned system trains on; nothing records reactions today.
3. **Model-over-retrieved-memory** — the LLM handles the semantic residue rules can't (e.g. "is this
   about a thing I'm tracking"), reasoning over `engram` via `rag_lib`. First real exercise of
   `llm_engines` structured output + `engram` + `rag_lib` against a daily workload.
4. **Summarization** — digest-by-gist; one-line summaries of surfaced mail. **Pullable forward** (low
   stakes — read not sent; model-simple; independent of the learning loop). Sprints 1+4 are the
   minimum that delivers the "go through email faster" goal.
5. **Conversational retrieval** — chat with the mail ("find my conference thread"); semantic retrieval
   via `rag_lib`, grounded answers with **visible sources**.
6. **Voice-conditioned drafting** — replies in the maintainer's style, conditioned on sent mail,
   **human-approved always**. Highest stakes (leaves the machine under the user's identity), lowest
   correction signal — comes last, stays most firmly human-in-the-loop.

## Settled parameters

**Memory model.** `engram` is the substrate, holding **two observation types**: *behavioral* (how the
maintainer reacted — feeds priority/voice profile) and *substantive* (commitments, facts,
appointments, decisions — the activity-extractor's output). These are retrieved for different purposes
and the schema should distinguish them from the start. The **wiki is NOT an auto-sink** — it is a
curated knowledge store that accepts only **human-gated promotions** of vetted memories. Email flows
freely into engram, selectively (human-confirmed) into the wiki. Auto-ingesting email into the curated
wiki would flood it the way keyword rules flooded the urgent tier; the maintainer's own finding
(deterministic curation dominates LLM adjudication) argues against it.

**The LLM's role.** Never where a rule suffices (deterministic-floor-first). The model earns its place
only for: semantic classification, summarization, grounded retrieval-answers, voice drafting. Always
**advisory, never actuating** — nothing sends, deletes, or archives autonomously. The deterministic
layer handles the easy majority; the model handles the genuinely-semantic residue, gated behind rules.

**Grounding discipline.** Anything the model asserts about the mail traces to a retrievable source the
maintainer can open and verify. Propose-then-verify, visible sources, no free synthesis. (Direct
application of the netflow hallucinated-citation lesson and the dormant citation verifier.)

**Data boundaries.**
- Personal mail — **yes**; the clean, sufficient corpus (five Gmail accounts, years deep). Persona
  research shows this class of data is enough to learn voice and priorities.
- DoD/work mail (Air Force, Army Outlook) — **out, permanently.** Accreditation, not privacy: a
  personal workstation is not an authorized system for controlled information, "local/private" does
  not change that, and the corpus can't be certified clean. Marginal benefit, highest-consequence
  risk, and a different (formal) register that may degrade a personal-voice profile anyway.
- Teams — **deferred**, gated on NPS work-tenant governance (raise with the institution first) and a
  cloud/OAuth ingestion path that breaks the local-first property. A deliberate later decision, not a
  drop-in source.
- The rule: **only data the maintainer can fully account for.**

**Interface.** File-first for rules (also the substrate any future GUI would edit). A GUI's real
justification, if ever, is the **conversational** surface (sprint 5), where interactivity is the point
— not rule management, which a file handles fine.

## The shared-foundation insight

The `rag_lib` retrieval layer is the single substrate under **learning, drafting, summarization, AND
chat**. Build it once → four capabilities. This is why it is the high-leverage investment and why it
matures the library against a real workload.

## How this matures ai_tools (the forcing function)

Each sprint exercises a library against real use and exposes its gaps: rule engine (none — deliberate
deterministic groundwork); instrumentation + memory (`engram` as preference memory — does it persist
and retrieve usefully?); model layer (`llm_engines` structured output + `rag_lib` retrieval on a real
corpus); the deterministic-then-model decision is itself the reusable propose-then-verify primitive,
now validated on a third domain after diagnostics and curation — repeated necessity is the admission
filter. Build the small real thing; let daily use teach the next move.

## Immediate next step

**Sprint 1 — the deterministic personal-rule engine**, built lightweight (thin scope → build against
real mail → correct), matching weight to risk (a rule file, not a security boundary). It is both the
usable tool that buys back the maintainer's morning and the foundation everything downstream sits on.

The next thread should first draft and ratify `SPEC-MAIL-01-personal-rules.md`. Do not fold behavioral
instrumentation, summarization, model classification, memory ingestion, retrieval, drafting, or UI
into that spec; each requires its own forcing result and thin follow-on spec.
