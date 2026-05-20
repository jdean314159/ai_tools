# engram-ui

`engram-ui` is the Streamlit sandbox and reference UI for the full `engram`
memory runtime.

It is packaged separately from `engram` so the memory runtime can remain usable
without Streamlit or UI dependencies.

## Install

From the monorepo root:

```bash
make install
```

The root `Makefile` installs this package in editable mode after `engram`.

## Run

From the monorepo root:

```bash
make run-ui
```

The UI is intended for local inspection of memory behavior, model/runtime
configuration, and teaching-oriented diagnostics.
