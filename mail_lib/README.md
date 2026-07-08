# mail_lib

Deterministic local mail helpers for Thunderbird-backed workflows.

`mail_lib` reads Thunderbird profile data and local mbox files without mutating
them. It provides the mail records, personal-rule loader, indexing helpers, and
triage primitives used by `examples/mail_assistant`.

The package deliberately contains no model calls and no network mutation path.
Server-side actions such as Move-to-Trash live in the separately configured
mail-assistant application layer.

Public entry points are exported from `mail_lib.__all__`.
