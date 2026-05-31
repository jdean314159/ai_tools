# diagnostics_agent

Read-only diagnostics spine for the diagnostics agent project. This package can
run fixed diagnostics commands inside a locked-down container with read-only
mounts, no network, dropped capabilities, resource limits, and guaranteed
cleanup. It also includes deterministic log triage that reduces raw log text
before any model sees it.

**Status: active campaign, not a frozen reference.** This example is the current
co-evolution driver for `ai_tools` (see `docs/projects/diagnostics_agent/`). Its
public-facing shape may still move. Treat it as a worked, in-progress
demonstration of composing `llm_engines` (and, in later phases, `engram` /
`llm_inspector`) -- not as a stability-committed library.

The package intentionally includes no remediation capability and no
LLM-generated commands. Collection commands are fixed and operator-configured.

---

## Setup

### Environment (per machine)

Virtual environments are **not portable** — shebang lines and symlinks are
bound to the Python that created them. Do not copy `.venv` between machines;
recreate it on each.

`diagnostics_agent` depends on `llm_engines` (which depends on `llm_harness_core`),
neither of which is on PyPI. Install them editable in dependency order:

```bash
rm -rf ~/ai_tools/.venv                         # remove any copied venv
python3 -m venv ~/ai_tools/.venv
source ~/ai_tools/.venv/bin/activate
pip install --upgrade pip

cd ~/ai_tools/llm_harness_core && pip install -e .
cd ~/ai_tools/llm_engines      && pip install -e .
cd ~/ai_tools/examples/diagnostics_agent && pip install -e ".[ui]"
```

A `setup.sh` at the repo root running these three installs makes fresh-machine
setup a one-liner and documents the dependency order.

### Container runtime

Install or enable rootless Podman, then pre-pull the image:

```bash
podman pull docker.io/library/alpine:3.20
```

Docker can be used by setting `SandboxConfig(runtime="docker")`, but Podman is
the preferred runtime for this project.

For rootless Podman, use `fuse-overlayfs` for the user storage driver path. This
avoids repeated kernel `overlayfs ... does not support file handles, falling back
to xino=off` warnings on container start, which otherwise dominate the diagnostic
journal output on some hosts.

```bash
sudo apt install fuse-overlayfs
mkdir -p ~/.config/containers
cat > ~/.config/containers/storage.conf <<'EOF'
[storage]
driver = "overlay"

[storage.options.overlay]
mount_program = "/usr/bin/fuse-overlayfs"
mountopt = "nodev"
EOF
```

If this config is added after rootless Podman storage already exists, reinitialize
or migrate that user storage before relying on the warning profile:

```bash
podman system migrate
# If warnings persist and you can discard local user containers/images:
podman system reset
podman pull docker.io/library/alpine:3.20
```

### Journal access

Add your user to the `systemd-journal` group for system journal read access.
Never run the tool as root.

```bash
id -nG | grep systemd-journal || sudo usermod -aG systemd-journal "$USER"
# then start a new login session, or:
newgrp systemd-journal
```

---

## Usage

### Streamlit UI

```bash
cd ~/ai_tools/examples/diagnostics_agent
source ~/ai_tools/.venv/bin/activate
streamlit run src/diagnostics_agent/ui/app.py    # opens http://localhost:8501
```

The UI lists local Ollama models annotated with a VRAM-fit estimate, collects
`journalctl -o json` records for the selected priority and time window, triages
the output deterministically, and asks the selected local model for an
interpretation. Runs only on explicit button click; changing controls does not
re-run inference.

### Python API

```python
from diagnostics_agent import ReadOnlySandbox, SandboxConfig

sandbox = ReadOnlySandbox(
    SandboxConfig(mounts=(("/var/log", "/logs"),))
)
result = sandbox.run(["cat", "/logs/sample.log"])
print(result.stdout)
```

Deterministic triage operates on caller-supplied strings or lines. It does not
read files, invoke containers, or call subprocesses.

```python
from diagnostics_agent import LogTriage

summary = LogTriage().triage(result.stdout)
print(summary.to_dict())
```

Structured interpretation consumes an existing triage summary and an injected
`llm_engines` engine. By default, only known local backends (`ollama`,
`llamacpp`, `vllm`, and `mock`) are accepted so log content such as IPs,
usernames, and authentication failures does not leave the host. Unknown backends
are refused unless `allow_remote=True` is set explicitly.

```python
from diagnostics_agent import LogInterpreter

interpretation = LogInterpreter(engine).interpret(summary)
print(interpretation.summary)
print(interpretation.security_risk, interpretation.operational_risk)
```

This is still not an orchestrator: callers decide how to collect logs, triage
them, and pass the summary to the interpreter.

The current locality guard is backend-name based. A more durable follow-up is to
inspect the resolved endpoint and treat loopback URLs or Unix sockets as local
even when they are accessed through an OpenAI-compatible adapter.

**Pointing at a trusted LAN host** (e.g., a workstation running the larger model
while the laptop collects): point the engine at the workstation's LAN address.
The guard passes it because the backend name is `ollama`. This is appropriate for
your own trusted network; it is not appropriate for cloud endpoints.

The end-to-end orchestrator composes fixed host-side collection, optional
sandboxed reading of the staged output, triage, interpretation, and an audit
record:

```python
import os

from diagnostics_agent import (
    CommandCollector,
    DiagnosticsOrchestrator,
    LogInterpreter,
    LogTriage,
    ReadOnlySandbox,
    SandboxConfig,
)

collector = CommandCollector(
    [
        "journalctl", "-o", "json", "-p", "warning",
        "--since", "-24h",
        "--output-fields=PRIORITY,MESSAGE,SYSLOG_IDENTIFIER,"
                        "_COMM,CONTAINER_NAME,_SYSTEMD_UNIT,USER_UNIT",
    ],
    source_description="journalctl warnings from the last 24 hours",
)
sandbox = ReadOnlySandbox(
    SandboxConfig(
        user=f"{os.getuid()}:{os.getgid()}",
        extra_run_args=("--userns=keep-id",),
    )
)
result = DiagnosticsOrchestrator(
    collector=collector,
    triage=LogTriage(),
    interpreter=LogInterpreter(engine),
    sandbox=sandbox,
).run()
print(result.audit)
```

The collector runs on the host and writes stdout to an ephemeral staging file.
The sandbox reads only that staged file through a read-only mount. If
`sandbox=None`, the orchestrator reads the staged file directly on the host as a
fallback for systems without a container runtime.

---

## Triage behavior

The triage layer parses two formats:

- JSON journal records: `journalctl -o json`
- ISO / `journalctl -o short-iso`: `2026-05-29T14:03:11-07:00 host proc[pid]: msg`
- Legacy syslog: `May 29 14:03:11 host proc[pid]: msg`

Use `journalctl -o json` for orchestrated runs. It preserves journald's numeric
`PRIORITY` field, which is more reliable than guessing severity from message
text. `short-iso` remains supported for plain-text inputs, but it does not carry
authoritative priority.

Legacy syslog timestamps do not contain a year. Pass `TriageConfig(assume_year=...)`
to produce dated records; otherwise those records keep `timestamp=None`. The
module never calls `datetime.now()`.

Every input line is represented in the output. Lines that cannot be parsed are
kept as unparsed records with their raw text intact. Low-severity non-finding
clusters are demoted into `suppressed` counts rather than dropped.

Template clustering masks volatile tokens before grouping:

- IPv4/IPv6 addresses: `<IP>`
- ports: `<PORT>`
- UUIDs: `<UUID>`
- hex values: `<HEX>`
- standalone integers: `<NUM>`

### Self-noise exclusion

The tool's own sandbox containers are named `diag-sbx-<uuid>`. Log entries
journald attributes to a container whose `CONTAINER_NAME` starts with `diag-sbx-`
are excluded from clustering and findings before any analysis. This prevents the
tool's own read-only enforcement tests from appearing as findings.

Exclusion is on by default (`TriageConfig(exclude_self_noise=True)`) and can be
disabled for debugging. Excluded entries are counted in `summary.excluded_self_noise`
and included in the conservation invariant:

```
findings + top_clusters + suppressed + excluded_self_noise == total_lines
```

The exclusion matches the structured journald `CONTAINER_NAME` field, not
message text. A message that merely contains "diag-sbx-" is not excluded.

### Journal volume and field projection

`journalctl -o json` emits full journal records (~2.7 KB per line). For a 24-hour
warning window, output can reach several megabytes. The `max_output_bytes` sandbox
cap (default: 1 MiB) will truncate large collections; `SandboxResult.truncated`
flags this.

Reduce per-line size dramatically with `--output-fields`, keeping only the fields
the triage uses:

```
--output-fields=PRIORITY,MESSAGE,SYSLOG_IDENTIFIER,_COMM,CONTAINER_NAME,_SYSTEMD_UNIT,USER_UNIT
```

This cuts each line from ~2.7 KB to a few hundred bytes (~7–10× reduction),
fitting a full day's warnings under the cap. journalctl always includes a small
set of mandatory fields (`__CURSOR`, `__REALTIME_TIMESTAMP`, `_BOOT_ID`) regardless
of `--output-fields`. The `--output-fields` list must be a superset of every
field the triage, rules, and self-noise exclusion consume; a test should assert
this so a future rule that reads a new field doesn't break silently.

Because journalctl output is oldest-first, truncation drops the **newest** entries
— the end of the window, closest to "now." For a "what's been happening lately"
check, this is the worst part to lose. Surface truncation as a visible warning,
not just a metadata flag.

---

## Default triage rules

The default rules are log-line patterns only. They do not inspect open ports,
process tables, disk usage, or other system state.

| name | category | severity | intent |
|---|---|---|---|
| `ssh_failed_auth` | auth | WARNING | sshd failed password or authentication failure |
| `ssh_invalid_user` | auth | WARNING | sshd invalid user or unknown user |
| `sudo_failure` | auth | WARNING | sudo authentication failure or incorrect password attempts |
| `pam_failure` | auth | WARNING | PAM authentication failure |
| `oom_kill` | memory | CRITICAL | out-of-memory or killed-process events |
| `disk_io_error` | disk | ERROR | I/O, buffer I/O, EXT4, ATA errors, softreset failed, reset failed, failed command |
| `segfault` | stability | ERROR | segfault or general protection fault |
| `kernel_bug` | stability | CRITICAL | kernel Oops, BUG, or Call Trace |
| `service_failed` | service | ERROR | systemd failed start or failed state |

The `disk_io_error` rule catches `ata\d+: softreset failed`, `reset failed`,
and `failed command` in addition to generic I/O error messages. This ensures
SATA softreset sequences — which are the most common disk-related warning on
real hardware — produce a triage finding and receive the deterministic operational
floor (see below).

---

## Interpretation output

The interpreter produces a structured `Interpretation` object with two
independent risk axes and a list of concerns. See ADR-012 for the full rationale.

```python
@dataclass
class Interpretation:
    reasoning: str       # model's free-text reasoning, generated first
    summary: str
    security_risk: str   # "none" | "low" | "medium" | "high" | "critical"
    operational_risk: str
    prioritized_concerns: list[ConcernAssessment]
    recommended_checks: list[str]

@dataclass
class ConcernAssessment:
    finding_ref: str
    rationale: str   # generated before severity — conditions the label
    severity: str
```

`security_risk` reflects compromise, credential exposure, or unauthorized access.
`operational_risk` reflects hardware failure, service degradation, or
data-integrity risk. They are independent: a disk softreset is high operational
risk and zero security risk simultaneously.

### Deterministic operational floor

After model output is validated, a deterministic step clamps `operational_risk`
and matching concern severities upward:

| Category | Finding severity | Floor |
|---|---|---|
| `disk`, `memory`, `stability` | ERROR | `operational_risk` ≥ medium |
| `disk`, `memory`, `stability` | CRITICAL | `operational_risk` ≥ high |
| `auth` | (any) | not clamped |

`auth` is excluded from the floor: auth risk is context-dependent (a screensaver
unlock and an sshd brute-force are both "PAM failure"; their severity differs by
service, count, and time pattern, not by presence). The model's calibrated
service-and-frequency judgment applies. Hardware and memory signals are "presence
implies concern" and are floored deterministically.

The floor only raises. A floored-but-confirmed-benign recurring signal (e.g., an
ATA softreset traced to standby wake latency) cannot be demoted without a
baseline/disposition store override — the correct channel for that, not relaxing
the floor.

### Calibration prompt guidance

The interpreter prompt explicitly instructs the model to:

- Weight auth findings by service (sshd/sudo/login = security-relevant;
  cinnamon-screensaver/polkit/gdm local unlock = usually benign) and by
  frequency (one failure ≠ attack).
- Treat hardware-failure indicators (disk/ATA errors, OOM, thermal) as
  warranting medium+ operational risk regardless of security implications.
- Answer only from the provided triage summary; state "not in the current
  results" rather than inventing system state.

The last point is the grounding instruction. Even with it, small models (≤3B)
have been observed fabricating kernel versions, OS names, and finding reference
IDs. The deterministic floor is the backstop; the grounding test is the gate.

### Local-only guard

The interpreter refuses remote backends (`openai`, `anthropic`) by default,
because log content includes IPs, usernames, and authentication failures that
must not leave the host. Pass `allow_remote=True` explicitly to override — only
appropriate for a self-hosted endpoint on your own trusted network.

---

## Model selection and hardware requirements

### Capability floor

Grounded log interpretation requires a model capable of:

1. Faithfully reading a structured summary without substituting training-era priors.
2. Calibrating severity by service context and frequency (auth), not just pattern.
3. Producing valid schema-constrained JSON under grammar enforcement.

Empirical testing across multiple models and hardware configurations established:

- **3B-class models are below the capability floor for this task.** Two separate
  3B models on a 4 GB laptop confabulated system facts (invented "Ubuntu 20.04 /
  kernel 5.13" on a 25.10 / 6.17 machine) and finding references (invented
  "DEP-1234" / "SEC-5678" codes that do not exist in the ruleset). A
  confabulating interpretation is worse than none — confident wrongness is more
  dangerous than silence.
- **4B-class models are marginal but viable**, especially with the deterministic
  floor reducing the model's judgment burden on hardware findings. Validate with
  the grounding test before trusting.
- **7B+ models** produce reliably grounded, calibrated output on workstation-class
  hardware. The workstation runs (3090, 24 GB VRAM) with qwen3:27b+ have been
  consistently accurate.

### Grounding test

Before trusting a model for interpretation, verify it does not fabricate system
facts:

1. Run a diagnostic on the target machine.
2. Check `uname -r` and `lsb_release -a` on that machine.
3. Verify the interpretation's summary and reasoning do not assert a kernel
   version or OS name that contradicts the real values.

Any model that emits an invented kernel version or OS name is disqualified for
the interpretation layer regardless of how fluent its prose is. This test is
cheap and should be repeated when changing models.

### VRAM and the 4 GB constraint

A 4 GB GPU (e.g., GTX 1650) has roughly 3–3.5 GB available after the desktop
compositor takes its share. A 4B model at Q4_K_M is ~2.5–3 GB of weights plus
KV cache — it either OOMs outright or leaves no room for context. Options:

- **Q3_K_M or smaller quant of a 4B:** cuts weights to ~2–2.3 GB, leaving KV
  headroom. Pull a specific quant from Hugging Face via
  `ollama run hf.co/<repo>:<quant>` or directly as a GGUF Modelfile.
- **llama.cpp partial offload:** `-ngl N` puts N layers on GPU, the rest on CPU.
  Stack with `--flash-attn` and `--cache-type-k/v q4_0` first (shrink the KV
  cache, maximize GPU-resident layers) before spilling to CPU. CPU layers are
  slow — expect multi-minute interpretations.
- **Avoid `E4B` / MoE variants on 4 GB:** "effective 4B" describes compute cost,
  not memory footprint. Gemma-4-E4B at Q4 is ~4.84 GB of weights — it won't fit.
  Use a dense 3–4B model.

### Laptop-as-deterministic-collector pattern

If the laptop cannot fit a grounding-faithful model, use it as a **deterministic
collector only**:

1. Collection and triage run on the laptop (CPU work, no GPU required, fully
   trustworthy).
2. The triage summary is passed to the workstation's larger model for
   interpretation — either by pointing the laptop's `OllamaEngine` at the
   workstation's LAN address, or by transferring the summary manually.

The local-only guard passes a LAN-pointed `OllamaEngine` (the guard keys on the
backend name, not the endpoint). This is appropriate for your own trusted
workstation on your own network; it is not appropriate for cloud endpoints.

The deterministic triage layer has been consistently accurate across all
hardware and model sizes. The LLM interpretation layer is where quality
degrades. If in doubt about a model's grounding, the triage summary is the
trustworthy output.

---

## Tests

Unit tests validate the generated runtime argv and do not require Podman or
Docker:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  pytest tests/test_sandbox_argv.py
```

Integration tests require rootless Podman and the Alpine image above. They use
hermetic temporary files rather than real host logs:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  pytest tests/test_sandbox_exec.py
```

Triage tests need no container runtime and no network:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  pytest tests/test_triage.py
```

Interpreter tests use a stub engine and also need no model or network:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  pytest tests/test_interpret.py
```

Orchestrator unit tests use fake collectors and stub engines. The sandbox
read-path test requires Podman:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  pytest tests/test_orchestrate.py
```

Full suite:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
  pytest tests
```

---

## Known limitations

### Journal volume and truncation

`journalctl -o json` emits ~2.7 KB per line. A 24-hour warning window on an
active system can produce several megabytes, exceeding the `max_output_bytes`
sandbox cap. When truncated, the **newest entries are dropped** (journalctl
output is oldest-first). Use `--output-fields` projection and raise
`max_output_bytes` to 8–16 MiB as described in the triage section.

Until the field-projection fix is applied to `journalctl_collector`, run with a
narrower time window (`--since -2h`) or raise the priority floor (`-p err`) to
keep volume under the cap for complete analysis.

### `service_failed` rule and check-and-exit daemons

The `service_failed` rule fires on any non-zero exit from a systemd unit. Some
daemons legitimately exit non-zero as a signal (e.g., `status=8` for
snapd's `prompting-client` when AppArmor-prompting is disabled). These appear as
`inactive (dead)`, not `failed`, and are not restart-looping.

Before investigating a `service_failed` finding, check:
```bash
systemctl --user status <unit>          # or without --user for system units
```
If the unit is `inactive (dead)` and not in a restart loop, it is almost
certainly a check-and-exit, not a fault. A future refinement will weight the
rule by actual `failed`/restart-looping state.

### `overall_risk` vs concern consistency

The two risk axes are not automatically constrained to `≥ max(concern.severity)`.
A medium concern can sit under a low/none overall if the model rates the axes
independently. A deterministic clamp (raise each axis to the maximum severity of
its matching concerns) is planned but not yet implemented.

---

## Rootless Podman log-permission wrinkle

Under rootless Podman, container UID 0 maps to the invoking host user and a
non-root `--user` maps to a subuid. Real host logs such as `/var/log/auth.log`
are often owned by `root:adm` with `0640` permissions and may be unreadable from
the container. That is a permission-denied result, not a sandbox failure.

Do not loosen isolation to work around it. This finding informs the later choice
between a more permissive mapped user and the host-export staging pattern.

## Orchestrator staging permissions

The orchestrator uses the host-export staging pattern. Host-side collection runs
a fixed read-only command and writes the result into a temporary `0700` staging
directory. With rootless Podman, the sandbox can read that staged file when the
container user maps to the host user that owns the file. On this host the working
configuration is:

```python
import os
from diagnostics_agent import ReadOnlySandbox, SandboxConfig

sandbox = ReadOnlySandbox(
    SandboxConfig(
        user=f"{os.getuid()}:{os.getgid()}",
        extra_run_args=("--userns=keep-id",),
    )
)
```

This avoids making staged log content world-readable. Logs that require elevated
host privileges still require the operator to run the collection command with
sufficient privilege; the sandboxed read and interpretation path do not run
privileged.
