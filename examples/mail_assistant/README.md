# Local Mail Assistant

Fixture-first FastAPI/Jinja/HTMX consumer specified by
`docs/projects/mail_lib/SPEC-MAIL-02-assistant-app.md`.

By default, the app reads the profile marked `Default=1` in
`~/.thunderbird/profiles.ini`. Set `MAIL_ASSISTANT_PROFILE` to override it, and
optionally configure `MAIL_ASSISTANT_RULES`, `MAIL_ASSISTANT_DB`,
`MAIL_ASSISTANT_BACKEND`, and `MAIL_ASSISTANT_MODEL`. From the repository root,
install or refresh the editable workspace packages after cloning or moving the
checkout:

```bash
make install
```

Then start with:

```bash
.venv/bin/python -m examples.mail_assistant.web_app
```

The example expects the repository's `mail_lib`, `llm_engines`, and
`llm_harness_core` to be importable; the root development installation provides
them. Its own package metadata declares only third-party web dependencies so it
does not try to resolve unpublished sibling packages from PyPI.

The server rejects non-loopback bind hosts. Real mail remains local and must not
be added to fixtures or sent to remote development or evaluation services.

The app stores a local JSON snapshot in its own SQLite database. Snapshots are
scoped to the active days/weeks window and record their coverage. Later startups
render the cached snapshot immediately while a fresh default-window scan runs in
the background. If a wider window is requested than the current snapshot covers,
the app starts or queues a wider background refresh. **Refresh snapshot** is also
non-blocking; reload the page after the background refresh completes.

Section summarization is explicit and deterministic at the prompt boundary. The
app allocates the configured input-token budget across every message in the
section and rejects a section when even its headers cannot fit. The model call
runs off the event loop and has a configurable soft timeout.

The **Stats** view computes sender and domain volume directly from the current
snapshot for the selected days/weeks window. It reports total and unread counts,
share of window mail, and most recent date. Rows link to exact sender/domain
list filters and can preview an ordinary reviewed personal-rule proposal. Stats
use no model, network call, or persistent historical table.

`static/htmx.min.js` is the pinned HTMX 2.0.4 browser distribution from the
official `bigskysoftware/htmx` release. See `static/HTMX-PROVENANCE.txt`.

## Move to Trash

Server-side trashing is disabled until an IMAP account file exists at
`~/.config/mail_assistant/imap_accounts.toml` (override with
`MAIL_ASSISTANT_IMAP_ACCOUNTS`). Passwords are never stored in that file; each
account names an environment variable containing its password or app password:

```toml
[[account]]
host = "imap.example.com"
username = "user@example.com"
password_env = "MAIL_ASSISTANT_IMAP_PASSWORD_1"
trash_folder = "Trash"
port = 993
```

Export the named variable before starting the app. Add one table per account.
The host and username must match Thunderbird's folder URI; Gmail commonly uses
`trash_folder = "[Gmail]/Trash"`. The app requires IMAP `MOVE`, searches the
selected source folder for exactly one matching `Message-ID`, and presents a
second confirmation before mutation. It does not fall back to copy/delete or
write Thunderbird mbox files.

Select one or more message-row checkboxes, then choose **Review selected for
Trash…**. The proposal lists every selected sender, subject, account, source,
and destination. Confirmation is bound to that exact selection. Moves execute
sequentially within each selected account; the outcome page reports each
success, failure, or message skipped because it left the snapshot. Only
successful moves disappear locally. Collapsed ignore groups provide a
client-side select-all control; selection alone never authorizes a move.

Messages already observed in a configured Trash folder are filtered out of the
assistant snapshot, so they do not appear in message lists, all-view results, or
Stats denominators.
