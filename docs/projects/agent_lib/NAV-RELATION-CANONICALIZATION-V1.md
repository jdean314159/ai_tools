# NAV relation canonicalization v1

**Status:** Frozen before production task selection  
**Version:** 1

This scoring-side contract applies identically to model claims and AST-oracle
relations. Prompts may describe it, but correctness never depends on the model
emitting the canonical string form directly.

## Rules

1. Source paths become repository-relative POSIX paths.
2. The module prefix derived from a source path is removed from Python symbols.
   `sample.Pipeline.ingest` therefore becomes `Pipeline.ingest`.
3. Class, method, and nested-function qualification is preserved. No case
   folding, typo repair, fuzzy matching, or suffix guessing occurs.
4. Call targets are parsed as Python expressions. If the expression is a call,
   arguments are removed by selecting its AST `func` node:
   `self.store.add(value)` becomes `self.store.add`.
5. Name and attribute chains are accepted. Subscripts, lambdas, returned
   callables, and other dynamic expressions fail closed.
6. The same normalization applies to relation `symbol`, `target`, and every
   ordered `path_symbols` entry.
7. Raw and normalized claims are both retained in scoring output.

## Admission rule

Canonical symbols must be fixture-wide unique. If stripping module prefixes
maps two definitions to the same symbol, the fixture is rejected before a
model run. Production task selection may not weaken this check after observing
model scores.

## Evidence rule

Canonicalization never changes evidence. The oracle records exact required
syntax lines:

- the definition line for a definition;
- the call line for a direct edge or named-site target;
- every component edge line for an ordered call path.

A claim must cite every required line. Extra cited lines are recorded as
`imprecise_claims` and fail exact correctness. This separates relation accuracy
from broad evidence ranges without silently accepting either.

Any change to these rules requires a new canonicalization version and a fresh
predeclared validation campaign. Version 1 must not be adjusted in response to
production task scores.
