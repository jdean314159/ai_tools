# ADR-013: Phase 3 vetted-catalog design and inference-only constraint

**Date:** 2026-05-31
**Status:** Accepted
**Deciders:** Jeff Dean
**Related:** `diagnostics_agent/`, `docs/projects/diagnostics_agent/CAMPAIGN.md`,
ADR-012 (risk model), ADR-011 (agent execution isolation)

---

## Context

The read-only diagnostics tool surfaces findings and recommended checks but
cannot chase them: "run smartctl on ata10," "check dmesg around the softreset"
are things the operator does by hand. A Phase 3 capability would let the tool
fetch additional context autonomously — pulling dmesg output around a flagged
device, fetching SMART status when a disk finding surfaces — rather than leaving
the operator to do the follow-up manually.

Two Phase 3 designs were considered:

**Option A — Free generation (RLM).** The interpreter produces a natural-language
description of what it wants to know, and a code-generation step writes a read
command (shell, Python) that runs in the sandbox.

**Option B — Vetted parameterized catalog.** The interpreter selects a named
check from a pre-authored catalog of read-only commands and supplies validated
parameters. The tool runs exactly that command with those parameters.

The choice is a security/capability trade-off. The tool's founding constraint —
"local-only, sandboxed, propose-not-execute, fail-loud, auditable" — is what
makes it trustworthy for a security diagnostics use case. Phase 3 is the first
time the LLM influences *which commands run*, which makes the design of that
influence the central question.

A separate question was raised: whether CISA's Known Exploited Vulnerabilities
(KEV) catalog could be integrated into the check workflow to surface
actively-exploited CVEs alongside log findings.

---

## Decision

### Phase 3: vetted parameterized catalog (Option B)

The Phase 3 design is a **check catalog**: a structured YAML document enumerating
the commands the tool may execute in Phase 3. The interpreter selects a catalog
entry and supplies parameters; the tool validates the parameters and runs the
pre-authored command as argv (never through a shell). The LLM cannot construct
or modify commands — it can only name a catalog entry and provide typed inputs.

Catalog entry shape (to be finalized in the catalog build):

```yaml
- id: dmesg_device_context
  trigger_category: disk
  description: Pull kernel messages around a named ATA/SCSI device
  argv: ["dmesg", "--color=never"]           # fixed; parameters are filter-side
  parameters:
    - name: device_pattern
      description: ATA port or device name to grep (e.g. "ata10")
      validation: "^(ata|sd|nvme|usb)[a-z0-9]+$"
  privilege: none
  read_only: true
  interpretation_note: |
    A "softreset failed → link up → configured" sequence is standby wake
    latency, not hardware failure. Look for link speed downshifts (3.0/1.5 Gbps
    vs 6.0 Gbps) or persistent resets without recovery as the failure signature.
```

Key properties:
- Commands are authored by a human and version-controlled alongside the tool.
- Parameters are validated against explicit patterns before any execution.
- Commands run as argv in the existing `ReadOnlySandbox`, not in a shell.
- Every catalog entry carries an explicit `read_only: true` assertion and a
  `privilege` flag; entries requiring elevation are gated separately.
- The catalog also serves as a **grounding reference for `recommended_checks`**
  in the current read-only tool: the interpreter's recommended checks are drawn
  from catalog descriptions, making them actionable and accurate rather than
  free-text approximations that may hallucinate flags or tool names.
- As a secondary benefit, the catalog is a human runbook: operators can consult
  it independently of the tool.

### Why not free generation (Option A)

Free generation requires the sandbox to contain **untrusted, model-written
code**. Even inside a locked-down container, a model-generated command that
reads broadly across the filesystem, exfiltrates to a world-readable path, or
exploits a `--no-sandbox` flag in a subprocess call is a meaningful threat
surface for a security tool. The sandbox reduces blast radius but does not
eliminate it.

A vetted catalog reduces that surface to **parameter injection** — a much
smaller, well-understood problem (reject non-matching parameters; build argv,
never shell-quote). A catalog also makes the tool auditable: the question "what
commands can this tool run?" has a complete, human-readable answer in a single
file. Free generation has no such answer.

The capability cost is real: the catalog can only pursue follow-ups the author
anticipated. A novel finding with no catalog entry cannot be explored until an
entry is added. This is the correct trade for a security diagnostics tool: it is
better to leave a finding unresolved than to run an unreviewed command.

### CISA KEV integration: rejected

The CISA Known Exploited Vulnerabilities catalog was proposed as a way to enrich
findings with active-exploitation context. It is rejected as a direct integration
for this tool for two reasons:

**Layer mismatch.** The diagnostics tool reads system logs — kernel messages,
auth events, service failures. CISA KEV lists CVEs in *software products*
(Palo Alto PAN-OS, Microsoft Exchange, Cisco SD-WAN Manager). A disk softreset
or a screensaver PAM failure has no relationship to a KEV entry. KEV describes
the enterprise attack surface (network appliances, server software); a Linux
workstation's journal has essentially zero overlap with that population.

**Wrong input type.** KEV integration requires a software inventory matched
against CVE data — a vulnerability scan, not log triage. The correct tool for
"do I have KEV-listed software?" is a scanner (grype, trivy, OpenSCAP) that
enumerates installed packages and matches versions; KEV is then a
prioritization overlay on the scanner's output. That is a separate capability
with its own architecture, not an extension of the log-triage check catalog.

If a vulnerability-scan module is built in the future, KEV would be appropriate
as a priority-override input: of the CVEs your scanner finds, flag those in KEV
as actively exploited and patch-first. That module would live alongside, not
inside, the diagnostics tool.

---

## Consequences

**Positive:**
- The Phase 3 design preserves the tool's auditable, bounded character. "What
  can this tool do in Phase 3?" has a one-file answer.
- Parameter validation (pattern-matching against explicit regexes; argv not
  shell) closes the injection surface at a well-understood boundary.
- The catalog does useful work before Phase 3 is built: grounding
  `recommended_checks` today, serving as a human runbook.
- The catalog grows incrementally: each time an operator runs a follow-up
  command by hand, that command is a candidate for catalog addition — co-evolution
  rather than up-front specification.

**Ongoing constraints:**
- Phase 3 gating: the catalog must exist and be reviewed before Phase 3 is
  activated. The `FollowupChat` Q&A layer (spec: `FOLLOWUP_QA_BUILD_SPEC.md`)
  explicitly cannot trigger catalog entries — it is read-only over results
  already in hand. The catalog execution path is a separate, explicitly-gated
  capability.
- The tool remains inference-only until Phase 3 is deliberately opened. Any
  implementation that runs a command in response to a chat turn, a model
  suggestion, or an `allow_fetch` flag is a Phase 3 capability and must go
  through the catalog + sandbox path, not appear as a side effect of another
  feature.

---

## Alternatives considered

**Free generation with a stricter sandbox.**
The sandbox is already near-maximal (no network, read-only root, dropped
capabilities, no new privileges, resource limits). Adding further restrictions
(seccomp profile, read-only bind mounts to specific paths only) reduces but does
not eliminate the attack surface of model-written code. The marginal sandbox
hardening required to responsibly contain free generation exceeds the benefit
of the flexibility it provides over a catalog.

**KEV as an enrichment layer on auth/network findings.**
A narrower KEV integration — checking log-derived indicators (source IPs of
failed logins) against threat-intel feeds — is more plausible than full CVE
matching. However, KEV is not an IOC/indicator feed; the relevant feeds for that
use case are third-party blocklists (abuse.ch, AbuseIPDB). This introduces
network egress (breaking the air-gap-ready property), raises privacy concerns
(log-derived IPs sent to a third party), and produces low yield on a
single-user workstation where failed SSH connections are internet background
noise. Rejected for this tool; re-evaluate if a network-monitoring module is
built.
