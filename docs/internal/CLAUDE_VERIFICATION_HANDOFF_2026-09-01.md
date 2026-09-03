# Handover — ai_tools verification thread, Claude side

**Date:** 2026-09-01
**Purpose:** carry the verification ledger, open findings, and process state into a
new thread. The repositories supersede this document on any detail they cover.
**Do not restate the specs here.**

---

## 1. Where the work stands

This thread ran a Claude/Codex verification cycle across `ai_tools` and, briefly,
`llm-reliability-lab`. Codex implemented; Claude verified independently. Six
findings were raised by Claude, all six were fixed by Codex, and all six were
independently re-verified by Claude except where noted below.

Last tree Claude actually held and inspected:

- **`ai_tools` commit `49026eac3d2e24b02641bf9db0a76e94909e9386`**
  archive SHA-256 `78dd869926b3b581f8ef7bffbc2962b5aa589e83a3e73a860d1cf4ce45b9e93e`

Everything after that commit is **reported, not verified**.

---

## 2. Verification ledger

Status vocabulary follows the lab's ledger: `CLOSED` (independently verified,
naming what was checked), `REPORTED` (attested by the other party, not
independently checked), `OPEN`.

### CLOSED — independently verified by Claude

| Item | Scope of verification |
|---|---|
| Spark endpoint in shipped YAML (`cda69ca`) | Placeholder present; in-place override guidance names `~/.engram/llm_engines.yaml` and `LLM_ENGINES_CONFIG` |
| Recursive hygiene test (`cda69ca`) | Traversal reimplemented independently; negative control confirmed it **fires** on a planted leak |
| Root cleanup (`b3d2abe`) | `AGENT.md` reduced to pointer with no independent rules; every relative markdown link in the repo resolved — zero dangling |
| `not_declared` scoping | Gated on declared capability **and** protocol support (`isinstance(engine, ToolCallingModel)` / `LogprobModel`); one literal, one site; exceptions record type only |
| Thinking tri-state at call sites | `None` omits `extra_body` entirely — OpenAI backend 6 call sites, vLLM 5; verified at the helper, not the parser |
| Raw-payload omission | Three-way: included / `intentionally_not_recorded` / `not_reported_by_backend` |
| 12 artifact `record_id` digests | Reproduced from committed bytes with from-scratch canonicalization; survived the Ruff sweep and two cleanups |
| Fail-closed publication gate (`49026ea`) | Four conditions **executed**: no `.git` → 128; git returns non-zero → 127; git binary absent (`FileNotFoundError` injected) → `unavailable`; empty tracked set → fails. All return 1 |
| Dynamic distribution discovery (`49026ea`) | Derived from every `pyproject.toml` with a `[project]` table — **12 roots** found, not the 9 reported. Nothing enumerated |
| Byte scan, no suffix allowlist (`49026ea`) | Planted `.cfg` inside a distribution root — caught. Identical file in `docs/` — correctly ignored |
| Handoff generalization / provenance preservation (`49026ea`) | Both handoffs use `git rev-parse --show-toplevel`; frozen records retain machine paths (5 occurrences in NAV-VERIFIABLE, 1 in engram temporal) |

### REPORTED — not independently verified

| Item | Note |
|---|---|
| `0d0b0c3` — centralized publication gate | Superseded by `49026ea`, which Claude did verify |
| `3fd5fc24` — explicit empty-inventory rejection, scope documentation | Tree never received |
| All test counts, Ruff, mypy, `git diff --check` | No network in Claude's container — pytest, pydantic, ruff, mypy unavailable throughout. **Every Claude finding in this thread is from reading code and computing digests, never from running the test suite** |

### OPEN — engram, unaddressed as of the last tree inspected

Both on the semantic layer. Source under `engram/src/` was byte-identical
between the standalone engram archive and `ai_tools-ba535a3`.

1. **`get_facts()` bypasses the recall policy entirely.** Public method, calls
   `self.semantic.query_facts()` directly — no `recall_decision`, no tenant
   check. `search_episodes` *is* filtered and `get_paired_exchanges` inherits
   that filtering, so `get_facts` is the outlier. Contradicts
   `docs/trust_policy.md`'s claim that "an external retriever cannot bypass the
   policy," which is true only of `build_prompt`.

2. **Extracted facts carry no trust metadata.** `_extract_and_store_facts`
   writes `metadata={"role": ..., "session_id": ...}` and does not inherit
   trust/tenant/source/writer from the source episode despite receiving
   `source_episode_id`. Composition-time filtering covers the `semantic`
   origin, so **enabling a trust policy silently drops every extracted fact
   from prompts.** Fail-closed, so the direction is safe; the effect is
   undocumented.

   These compose in opposite directions: through `build_prompt` you get *no*
   facts; through `get_facts` you get *unfiltered* facts.

   The fix looks small — inherit from the source episode, available at the call
   site — but it asserts that a fact derived from a verified episode is itself
   verified. Defensible for extraction, not for inference. **That boundary
   belongs in an ADR, not in the extraction function.**

3. **Coverage gap.** `test_trust_policy.py` has ten well-chosen tests; none
   touches `semantic` or `get_facts`. The single `get_facts` test lives in
   `test_semantic.py` with no policy configured. Same shape as INC-017: the
   distinction was verified where it was reachable, and the path where it fails
   was not exercised.

### Never reviewed

- engram temporal memory, `evaluation.py`, `inspection.py`, the ~16 probe reports
- The `navigation_*.py` / `programming_*.py` module splits from the refactor
- ADR-028 seed plumbing beyond confirming `_apply_seed_preference` exists in the
  OpenAI backend call path

---

## 3. Claude's own corrections in this thread

Recorded because the pattern matters more than the individual errors.

**Root `.log` files — wrong finding.** Claude flagged four `.log` files at repo
root as clutter. They were **untracked working-directory copies**; the real
fixtures had been in `examples/diagnostics_agent/tests/fixtures/` all along.
One `git ls-files` would have settled it, and `.git` was present in that tarball
for the first time. Cause: the delivery method changed from `git archive` to
plain tar, which changed what "in the repo" meant, and Claude didn't adjust.
Class 7 — claim about an artifact one cheap command away. Deleting them was
right; the stated reason wasn't.

**Zero-width character analysis — two over-readings, both from skipping a null
baseline.** On a Medium article containing 1,505 zero-width characters, Claude
first inferred a weighted generator from lopsided symbol frequencies in a
36-symbol sample; at full scale the distribution was statistically
indistinguishable from uniform (chi-square 4.72, df 3). Then Claude claimed a
payload would not prefer mid-word positions; the null baseline is ~61% mid-word
in English prose, against 73% observed — a real 12-point enrichment, not the
decisive signal implied. Both fixed by the project's own NEURAL-07 rule: check a
signal against a null baseline before trusting what it appears to mean.

**Embeddings in the `not_declared` finding — narrower than stated.** Claude said
`unsupported` should survive for embeddings because it is genuinely detected.
There is no embedding probe in the suite, so it was never reachable there
either. The correct finding: `unsupported` was unreachable for *every* optional
probe, and only `MockEngine` declaring everything false made the status appear
to work.

---

## 4. Process discipline that actually fired

- **Digest-first, stop on mismatch.** One archive arrived with digest
  `77effa92…` against a stated `78dd8699…`. Claude stopped without reviewing
  and named the likely causes; it was the wrong file, and the correct one
  matched exactly on resend. **This is the practice to keep.** Ask for the
  commit hash alongside the digest — one archive could only be identified by
  digest because no hash was supplied.
- **`git archive` over plain tar.** Everything in it is committed by
  definition, so "is this in the repo" stops being a question Claude can get
  wrong. Use plain tar only for uncommitted work, and say which was sent.
- **The drafter cannot be the reviewer.** After the repo-wide Ruff sweep,
  Codex re-confirmed three closures it had implemented itself. Those stayed
  `REPORTED` until Claude re-verified them against the reformatted tree.
- **Material rewrites invalidate prior verification.** The 429-file Ruff sweep
  returned three CLOSED rows to REPORTED. Worth weighing before the next
  cosmetic pass: it produced zero behavioral change and cost a full
  re-verification round.
- **Negative controls, not assertions.** For every gate Claude verified in this
  thread, it planted a violation and confirmed the gate *fires*. Reading the
  assertion is not the same check.

---

## 5. Standing observations, no action requested

- **The publication gate cannot run on the artifact under review.** It fails
  closed without `.git`, which is correct — but it means "strict hygiene passed"
  is a claim about a checkout, never about the shipped bytes. `3fd5fc24`
  reportedly documents this.
- **The empty-tracked-set rejection was incidental before `3fd5fc24`** — it
  failed because fixture references stopped resolving, not because emptiness was
  asserted. Confirm the new guard is explicit and its test targets that branch.
- **The gate's AST fixture resolver has a soft edge.** A reference it fails to
  parse simply isn't checked, and nothing reports the gap — drift is toward
  false negatives. Deferral pending an observed failure is correct per the
  project's own build-only-when-a-run-fails rule.
- **v2 tool-recovery cases are at ceiling for both models**, so v2 is retired as
  an evaluation suite. In the v4 development run only `stale_success` was
  evaluation-eligible (3/5); five families sat at 5/5. A stronger model likely
  shrinks that set further — worth knowing before investing in v5.
- **Context retention needs a timing bound before scaling past 32K.** Measured
  2.66 s / 10.8 s / 38.0 s at 1K / 8K / 32K input tokens, roughly linear at
  ~1.16 ms per input token (~860 tok/s prefill). At 262K that is minutes per
  case with no timeout policy in the gate.
- **Seeding practice is inconsistent across profiles.** Context retention used
  seed 101, tool-recovery baseline seed 7, and the matched thinking pair
  `seed_requested: None` — on the one comparison where holding sampler variation
  constant across conditions would matter most. Legitimate under ADR-028
  (`not_requested` is a valid state); worth deciding whether matched
  comparisons default to a fixed seed, and recording the choice.

---

## 6. Hardware and model state

DGX Spark, 128 GB unified LPDDR5X, ~273 GB/s. Running
`Qwen3.8-Flash-Next-UD-IQ4_XS` (93.7 GB, 3 shards) via llama.cpp built for
`sm_121`, served on port 8080.

Observed: 94 GB resident, **26 GB available**, swap 0 used. Decode 26–28.5
tok/s. Thinking is **on by default** and `chat_template_kwargs.enable_thinking:
false` correctly suppresses it — confirmed by `reasoning_content` present in one
case and absent in the other.

Two facts worth carrying:

- **Q4_K_XL (111 GB) would not have fit.** Total usable is 121 GB, not 128.
  IQ4_XS was the right call by a wider margin than estimated.
- **`enable_thinking` changes the prompt, not just decoding.** Identical user
  message produced 63 prompt tokens with thinking on, 23 with it off. Prompt
  token counts are not comparable across thinking conditions — worth a
  limitation line if any campaign reports them.
- **`--jinja` is required.** Without it there is no tool calling and
  `enable_thinking` is ignored, so probes fail in ways that look like model
  failures.
- **Unified memory means `--n-gpu-layers` below max frees nothing.** CPU offload
  is not a memory lever on this box. `-ot per_layer_token_embd.weight=CPU` is a
  discrete-GPU technique; useful here only if the CUDA allocator fails while
  system memory remains free.

---

## 7. Recommended next steps

1. **Send the `3fd5fc24` tree** (`git archive`, with digest *and* commit hash) if
   independent closure of the last three items matters. Check: the empty-set
   rejection is an explicit guard rather than a side effect; the new test targets
   that specific branch; scope documentation sits where someone running `make`
   would meet it.
2. **The two engram findings are the only unaddressed defects Claude found.**
   Finding 2 needs an ADR before a fix — the trust-inheritance boundary is a
   durable decision, and engram's own stated principle is that applications
   assign trust and Engram only validates it.
3. **Design the next campaign with headroom.** ADR-029's gate has now stopped
   two campaigns correctly. Whatever comes next — v5 recovery, long context,
   concurrency — needs a baseline expected to fail some fraction, predeclared.
4. **Re-verify anything after another broad reformat.** The ledger rule applies
   regardless of who ran the formatter.

---

## 8. Working agreements (carried forward, unchanged)

- Claude specifies and verifies; Codex implements. Neither attests to work only
  the other performed.
- Verification scope is stated exactly — what was checked, by whom, against
  what — never a bare "verified."
- Archives exchanged as `git archive` with SHA-256 stated upfront **and the
  commit hash**; the receiver verifies the digest before reviewing and stops on
  mismatch.
- Digests are independently reproduced from a from-scratch canonicalization,
  never trusted from a stated hash or a single script's own output.
- New acceptance-gate semantics require explicit user authorization, distinct
  from either AI party's recommendation.
- Where a claim can be settled by opening a file, running a script, or fetching
  a versioned source, do that before writing the paragraph that asserts it.

---

## Codex addendum — repository state after Claude's inspected tree

This addendum is **reported by Codex, not independently verified by Claude**.

- Current commit before adding this handoff: `3fd5fc24a351774c0b0220c4da153d88b9072376`.
- `3fd5fc24` explicitly rejects a successful-but-empty `git ls-files` result;
  its direct negative test targets that branch rather than relying on fixture
  tracking to fail incidentally.
- The standing docs distinguish checkout publication hygiene from separate
  archive-byte/digest verification.
- Codex reports the offline suite at 1,254 passed and 305 skipped, Ruff passing,
  strict checkout hygiene passing, and a clean worktree at that checkpoint.
- Claude's two Engram semantic trust findings remain open. No implementation or
  ADR decision has been made in response to them.
