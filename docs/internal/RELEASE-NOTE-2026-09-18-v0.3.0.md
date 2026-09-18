# v0.3.0 pre-release path review

**Date:** 2026-09-18

Before tagging `v0.3.0`, the committed tree was scanned for workstation paths.
The scan found 88 occurrences of the local `/home/<workstation-user>` prefix in
67 files: 62 serialized artifacts, three Markdown records, and two Python
test/tool files. Sixty of the
serialized files are frozen oracle-localization transcripts whose exact bytes
are bound by transcript digests in their run metadata.

Every affected file was already present on public `origin/main`; none was
introduced by the four then-unpublished commits proposed for the release. The
paths were not rewritten because doing so would mutate frozen, digest-bound
evidence while failing to remove the original bytes from already-public Git
history. This is an inherited publication condition, not evidence that the
paths are safe or desirable in new artifacts.

From this release forward, newly committed artifacts and traces must use
repository-relative paths, basenames, or explicit redacted placeholders rather
than workstation-absolute paths. Evidence that genuinely requires an absolute
host path stays outside the public repository or records a non-sensitive digest
and a disclosed redaction instead.
