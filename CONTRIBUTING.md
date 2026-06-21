# Contributing

## What belongs in this repo

Before adding a package, tool, or example, read
[`docs/internal/MEMBERSHIP.md`](./docs/internal/MEMBERSHIP.md). Every addition
must answer: *is this a reusable building block that an outside developer would
import and use?* If not, it belongs elsewhere.

## Build and test

```bash
make install      # creates .venv, installs all packages in dependency order
make test-core    # default suite — no GPU, no network required
make install-gpu  # optional: CUDA PyTorch and GPU-backed features
make test-ml      # optional: torch-dependent tests
```

A plain `make install && make test-core` must pass on a fresh clone before any
commit is merged.

## Publication hygiene

```bash
python scripts/check_publication_hygiene.py
```

Must pass cleanly. The script checks for build artifacts in the git index,
required root documents, and legacy file patterns. Run it before pushing.

## Architecture decisions

Significant decisions are recorded in [`adr/`](./adr/) using the existing ADR
format. See [`ADR_INDEX.md`](./ADR_INDEX.md) for the index and the template.

## Package maturity tiers

Each package declares a tier in its README: **stable**, **beta**, or
**experimental**. Do not promote a package's tier without verifying the public
API is stable and the quickstart works on a fresh install.
