# Agent command-isolation characterization — 2026-08-31

## Question and frozen boundary

Does `agent_lib.programming.execute_workspace_command` actually use its selected
Docker boundary without host fallback, permit the intended workspace mutation,
hide a host-only file outside the bind mount, and deny worker network access?

Profile `agent_lib.command_isolation`, version 2 freezes three deterministic
commands through the public execution function. It uses the already cached
`nvidia/cuda:12.4.0-base-ubuntu22.04` image, requests Docker explicitly, disables
networking, and forbids host fallback. No model or remote service is involved.
The artifact omits commands, outputs, paths, and environment values.

## Predeclared gate

All three cases must report the external Docker backend with no fallback. The
workspace-write case must create the expected file inside the mounted temporary
workspace. The host-escape case must not see a marker created immediately
outside that workspace, and the marker must remain unchanged. The network case
must fail to open a TCP connection while returning the probe's expected success
status.

## Disclosed invalid version 1

Version 1 reported a green gate, but post-run review found that its host marker
was created under the temporary parent while the command checked a different
fixed path. Its host-escape result is therefore infrastructure-invalid. The
artifact is retained rather than silently replaced:

`docs/projects/agent_lib/runs/2026-08-31-agent-command-isolation-v1.json`

SHA-256: `ef6d5d2eb3745ce87d83898aef6abe46a0045b6db51f74abbec70529ee507386`

Version 2 changes only that command to check the exact host-marker path.

## Version-2 outcome

Version 2 passed all three cases. Every result reported `docker` as the external
backend, network disabled, and no host fallback. The container wrote the
expected workspace file, could not observe the exact host-only marker outside
the bind mount, left that marker unchanged, and could not establish the frozen
TCP connection.

Artifact:
`docs/projects/agent_lib/runs/2026-08-31-agent-command-isolation-v2.json`

SHA-256: `d78a0e6a94e1607a94be6f1c68b719f8a4c7b952aad484ed00d7e00b2b46904b`

This is a bounded positive result, not a general sandbox-security claim. It
does not test container escapes, symlink attacks, daemon compromise, resource
limits, capabilities, seccomp, concurrent worktrees, or arbitrary network
destinations. ADR-011's recommended process-limit and `no-new-privileges`
controls are not implemented by the current container argv and remain open.
