# NAV-VERIFIABLE-00 deterministic foundation validation

**Date:** 2026-07-23  
**Status:** Contract gate passed; no live model result.

## Implemented boundary

The deterministic layer now provides:

- source-hash-pinned, versioned task fixtures;
- exact task contracts for definition lookup, direct callers, one unique call
  path, and a call expression at a named site;
- relation-aware structured claims for definitions, caller→callee edges,
  ordered paths, and mutation targets;
- a conservative Python AST oracle;
- observed-evidence-aware exact scoring;
- paired-run manifest validation that permits only one autonomous and one
  structured run with identical shared configuration.

The oracle does not infer runtime dispatch. It resolves module-local calls,
`self`/`cls` method calls, and explicit class-qualified calls. Aliases and
dynamically constructed calls fail closed. Same-named symbols require
qualification, nested-function calls are attributed to the nested function,
and indirect helper calls cannot satisfy a direct-edge claim.

## Deterministic result

The `agent_lib` package gate passed with `128 passed`. Dedicated tests cover all
four task shapes, exact relation scoring, indirect-as-direct rejection,
unobserved evidence, source hash drift, aliases, same-named methods, nested
functions, dynamic calls, relation-claim shape, and paired configuration drift.

The repository-root pytest command remains unavailable because the root
`conftest.py` imports a missing `examples._repo_bootstrap` module before test
collection. This is pre-existing and outside the NAV change; the supported
package-scoped gate was used.

## Not yet validated

This checkpoint does not show that a model can emit the relation schema, that
task-specific ledger goals work, or that the ledger improves any paired task.
The production task set and paired executable do not exist. No live run was
performed.

The next gate is model-facing adoption plus deterministic end-to-end tests:
seed each task's user-visible goals, require `relation_claims` only for this
track, preserve the autonomous mode on the same question, and score both run
records with the external AST oracle. Live runs remain premature until that
contract passes.
