# NAV-VERIFIABLE-00 paired structured-navigation evaluation

**Status:** First live paired campaign complete; frozen verdict inconclusive.

## Purpose

Measure whether an explicit information-goal ledger improves termination and
evidence discipline on repository-navigation questions whose answers are
decidable from local source structure.

This is a separate track from:

- `NAV-TEST-00`, the autonomous exhaustive-enumeration benchmark, whose failure
  status remains unchanged;
- `NAV-STRUCT-00`, the failed structured exhaustive-enumeration experiment.

Results must be reported as harness-structured navigation, never as autonomous
NAV performance.

## Confirmed reusable surfaces

The existing harness already provides:

- the same read-only `read_file`, `grep`, and `list_files` tool surface for both
  modes (`agent_lib/src/agent_lib/eval/repo_navigation.py`, lines 395–538);
- an opt-in complete goal ledger with deterministic transition validation
  (`agent_lib/src/agent_lib/eval/navigation_goals.py`, lines 70–169);
- an opt-in structured planner mode while autonomous defaults remain unchanged
  (`agent_lib/src/agent_lib/eval/repo_navigation.py`, lines 910–1120);
- structured final claims with evidence references
  (`agent_lib/src/agent_lib/eval/navigation_claims.py`, lines 12–147);
- source-backed syntactic validation that a claimed Python symbol encloses its
  cited evidence (`agent_lib/src/agent_lib/eval/navigation_claims.py`, lines
  150–294);
- cumulative token, step, tool-call, evidence, and claim telemetry in the
  existing scorer (`agent_lib/src/agent_lib/eval/repo_navigation.py`, lines
  1422–1518).

These references establish reusable mechanics only. The existing
ground-truth-region scorer does not establish exact caller or call-path
relations.

## Task shapes

The initial set should contain multiple pinned Python fixtures for each shape:

1. Locate a named definition.
2. Identify the syntactically direct callers of a named callable.
3. Trace one specified call path between named endpoints.
4. Identify the callable invoked at a named mutation call site.

Every task must have one exact structural answer derivable from the pinned
source snapshot. Avoid repository-wide “all mutations” or other open-world
completeness claims.

## Paired protocol

Each task is run twice against the same pinned source, relation-claim schema,
AST scorer, model configuration, budget, question, and seed:

1. no-ledger baseline with task-specific navigation goals disabled;
2. ledger run with task-specific navigation goals enabled.

Both arms emit identical typed `relation_claims` on the final action. No
free-form extraction or looser baseline rubric is allowed. The experiment
therefore isolates per-step ledger state under a shared structured-answer
contract; it is not NAV-TEST-00's free-form autonomous mode and cannot establish
whether final claims alone fix budget exhaustion.

Run order must be recorded and alternated across tasks to expose order effects.
Sampled trajectories mean a pair is a comparison unit, not proof that a seed
pins generation.

The planner receives the natural-language task in both modes. Structured mode
may receive goal identifiers and requirements copied from that task, but never
expected paths, symbols, line numbers, edges, or answer-key content.

## Exact scoring

The scorer runs outside planner context and compares structured claims with an
AST-derived oracle from the pinned snapshot:

- definition: exact qualified symbol and defining span;
- direct caller: an AST call edge from the caller body to the named callee;
- call path: the exact ordered edge sequence required by the task;
- mutation target: the exact call expression at the named site.

String presence is insufficient for relation scoring. Evidence references must
be observed, must overlap the relevant syntax node, and must identify the
correct enclosing symbol. Free-form prose is retained for audit but contributes
nothing to correctness.

## Metrics and decision gate

Report per pair:

- completed with an answer;
- exact structural correctness;
- unsupported claims and validation errors;
- evidence precision and recall;
- planner calls, tool calls, steps, and cumulative tokens;
- structured-minus-autonomous deltas for every metric.

Do not adopt the ledger unless it improves termination or exact correctness
across the task set without a material aggregate correctness regression. Token
cost is reported as a tradeoff, not hidden inside the aggregate.

The first live campaign requires deterministic scorer tests plus at least one
autonomous/structured pair for every task shape. No 8B portability campaign is
part of this gate.

Campaign v1 further requires at least fourteen admitted tasks: four local, four
intermediate, and six exploratory. The campaign is incomplete until every
admitted task has both paired outcomes recorded. Exploratory results carry the
primary termination-control hypothesis and cannot be pooled away by easier
tiers.

## Must be built (does not exist yet)

Implemented:

- Versioned, source-hash-pinned task fixtures and all four task shapes
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 22–159 and
  676–727).
- Relation-aware claim schema and shape validation
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 26–251).
- Conservative AST oracle for definitions, direct-call edges, unique paths,
  and named-site call expressions
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 323–590).
- Exact evidence-aware relation scoring
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 729–825).
- Paired-run manifest validation enforcing identical shared configuration and
  explicit alternating order
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 969–1007).
- Frozen, two-sided relation canonicalization with fixture-wide collision
  rejection and raw/normalized audit output. See
  `NAV-RELATION-CANONICALIZATION-V1.md` and
  `agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 592–674.
- Exact required-line evidence scoring for every path edge; broad ranges are
  reported as imprecise and cannot pass exact correctness.
- A source-only, hashed task-admission manifest with frozen local,
  intermediate, and exploratory tiers. See `NAV-TASK-ADMISSION-V1.md` and
  `agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 827–967.
- A campaign-level admission and reporting policy requiring exploratory
  diversity across three source snapshots, exact paired coverage, per-tier
  reporting, and only a secondary equal-tier macro-average. See
  `NAV-VERIFIABLE-CAMPAIGN-V1.md` and
  `agent_lib/src/agent_lib/eval/verifiable_campaign.py`, lines 26–472.
- Mechanical candidate enumeration, normalized-relation deduplication, a
  source-hashed pool, and deterministic stratified selection. See
  `NAV-CANDIDATE-SELECTION-V2.md` and
  `agent_lib/src/agent_lib/eval/verifiable_selection.py`, lines 27–298.
- Deterministic fixtures and tests for aliases, same-named methods, nested
  functions, indirect helper calls, unobserved evidence, hash drift, and
  dynamically constructed calls.

Still required before live use:

- No live-use requirement remains; this is an evaluation track, not a shipping
  runtime feature.
- A replicated campaign requires a separately predeclared protocol.

Production task snapshots and the selected campaign now exist under
`agent_lib/eval_snapshots/` and
`agent_lib/eval_manifests/nav_verifiable_campaign_v1/`. The deterministic
selection contains all four task shapes and the frozen 4/4/6 tier distribution.
The paired executable is
`agent_lib/examples/nav_verifiable_campaign.py`; it uses task-specific goals
only in the ledger arm, uses the same `relation_claims` schema in both arms,
alternates arm order, scores with the external AST oracle, and writes each arm
record before campaign aggregation.

Scoring reports four independent booleans:

- `relation_correct`;
- `evidence_complete`;
- `evidence_precise`;
- `exact_correct`, requiring all three plus no validation errors.

`unsupported_claims` is reserved for relations absent from the oracle.
Relations with missing required syntax lines appear under
`incomplete_evidence_claims`; over-cited relations appear under
`imprecise_claims`.

Aliases and dynamically constructed calls fail fixture validation. Ambiguous
calls are excluded from edge resolution, so any edge or path task that depends
on them fails to resolve exactly. A named-site mutation task may still identify
the literal call expression without asserting its runtime dispatch target.

## Assumptions to verify

- Production source snapshots contain enough statically resolvable examples
  for multiple tasks of all four shapes.
- Alternating run order is sufficient to control local engine cache/order
  effects for the first small campaign.
- The model emitted structurally valid relation claims on the trivial fixture
  (3/3 corrected formatter probes). Frozen canonicalization resolves the two
  string-form differences offline. The remaining formatter miss is broad path
  evidence (lines 7–14 instead of exact edge lines 8 and 11).

Difficulty is assigned before any run from hop count, answer-file count,
candidate-file count, and decoy count. Autonomous cost validates the tier
assignment but cannot alter it; calibration misses remain visible in reporting.
