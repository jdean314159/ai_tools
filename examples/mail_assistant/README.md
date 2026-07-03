# Local Mail Assistant

Fixture-first FastAPI/Jinja/HTMX consumer specified by
`docs/projects/mail_lib/SPEC-MAIL-02-assistant-app.md`.

Set `MAIL_ASSISTANT_PROFILE` to a Thunderbird profile and optionally configure
`MAIL_ASSISTANT_RULES`, `MAIL_ASSISTANT_DB`, `MAIL_ASSISTANT_BACKEND`, and
`MAIL_ASSISTANT_MODEL`. Start with:

```bash
python -m examples.mail_assistant.web_app
```

The example expects the repository's `mail_lib`, `llm_engines`, and
`llm_harness_core` to be importable; the root development installation provides
them. Its own package metadata declares only third-party web dependencies so it
does not try to resolve unpublished sibling packages from PyPI.

The server rejects non-loopback bind hosts. Real mail remains local and must not
be added to fixtures or sent to remote development or evaluation services.

Section summarization is explicit and deterministic at the prompt boundary. The
app adds whole messages in snapshot order until the configured input-token budget
would be exceeded; it rejects a section when even its first message cannot fit.
The model call runs off the event loop and has a configurable soft timeout.

`static/htmx.min.js` is the pinned HTMX 2.0.4 browser distribution from the
official `bigskysoftware/htmx` release. See `static/HTMX-PROVENANCE.txt`.
