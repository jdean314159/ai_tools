# NAV-VERIFIABLE-00 paired structured-navigation evaluation

**Status:** Deterministic foundation implemented; planner/runner adoption and
live paired campaign not built.

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

Each task is run twice against the same pinned source, model configuration,
budget, question, and seed:

1. autonomous baseline with structured navigation disabled;
2. structured run with the ledger enabled.

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

## Must be built (does not exist yet)

Implemented:

- Versioned, source-hash-pinned task fixtures and all four task shapes
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 20–142 and
  540–590).
- Relation-aware claim schema and shape validation
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 23–234).
- Conservative AST oracle for definitions, direct-call edges, unique paths,
  and named-site call expressions
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 275–538).
- Exact evidence-aware relation scoring
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 592–654).
- Paired-run manifest validation enforcing identical shared configuration and
  explicit alternating order
  (`agent_lib/src/agent_lib/eval/verifiable_navigation.py`, lines 656–694).
- Deterministic fixtures and tests for aliases, same-named methods, nested
  functions, indirect helper calls, unobserved evidence, hash drift, and
  dynamically constructed calls.

Still required before live use:

- Planner output-schema adoption for `relation_claims`.
- Task-specific goal seeding instead of the NAV-STRUCT-00 exhaustive ledger.
- A paired executable that runs both modes and writes the manifest plus scores.
- Production task snapshots with multiple fixtures per task shape; the checked
  fixture is a deterministic contract proof, not an evaluation dataset.

Aliases and dynamically constructed calls fail fixture validation. Ambiguous
calls are excluded from edge resolution, so any edge or path task that depends
on them fails to resolve exactly. A named-site mutation task may still identify
the literal call expression without asserting its runtime dispatch target.

## Assumptions to verify

- Production source snapshots contain enough statically resolvable examples
  for multiple tasks of all four shapes.
- Alternating run order is sufficient to control local engine cache/order
  effects for the first small campaign.
- The existing model can reliably emit the relation-aware claim schema once it
  is added to the planner contract.
