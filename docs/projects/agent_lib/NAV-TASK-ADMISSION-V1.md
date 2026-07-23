# NAV-VERIFIABLE-00 task admission v1

**Status:** Frozen before production task construction  
**Schema version:** 1

Candidate tasks are admitted and tiered entirely from pinned source structure.
No model output, token count, tool count, or observed success may change a
task's tier.

## Required admission checks

Every task must:

1. resolve to at least one exact AST relation;
2. use a source-hash-pinned fixture containing no unpinned Python files;
3. pass relation-canonicalization v1 without a fixture-wide symbol collision;
4. avoid aliases and dynamically constructed calls outside the conservative
   oracle;
5. record its raw structural difficulty features and derived tier in a hashed
   admission manifest.

## Structural features

- `hop_count`: number of required call edges; definitions use zero and
  named-site targets/direct edges use one.
- `answer_file_count`: distinct files containing required relation nodes.
- `candidate_file_count`: files containing the queried terminal identifiers
  before AST resolution.
- `decoy_count`: non-answer definitions or call sites sharing those terminal
  identifiers.

## Frozen tier policy

Local:

- exactly one candidate file;
- no more than one hop;
- zero decoys.

Exploratory requires at least two of:

- five or more candidate files;
- three or more hops;
- four or more decoys;
- three or more answer files.

Every admitted task not local or exploratory is intermediate.

## Calibration reporting

Autonomous baseline behavior validates this structural proxy but never rewrites
it. If an exploratory task completes cheaply, the result is reported as a tier
calibration miss. The task remains in its original tier and paired results are
reported both overall and by the predeclared tier.

Changing a threshold or feature requires task-admission schema version 2 and a
new candidate campaign. Version 1 may not be adjusted after observing run
outcomes.
