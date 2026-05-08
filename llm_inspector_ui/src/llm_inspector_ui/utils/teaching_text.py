from __future__ import annotations

from typing import Any

from llm_inspector_ui.state.models import RunArtifact
from llm_inspector_ui.utils.trace_access import (
    get_agent_execution_summary,
    get_agent_summary,
    get_evidence,
    get_retrieval_events,
    get_retrieval_summary,
    get_sections,
    get_token_accounting,
)


_AUGMENTER_LABELS = {
    "baseline": "control branch",
    "engram_lite": "lightweight memory branch",
    "engram": "advanced memory branch",
    "rag": "retrieval-augmented branch",
}


def _nonempty_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def describe_compare_group_for_teaching(runs: list[RunArtifact]) -> list[str]:
    names = [run.augmenter_id for run in runs]
    lessons: list[str] = []

    if "baseline" in names and len(names) > 1:
        others = [name for name in names if name != "baseline"]
        if others:
            lessons.append(
                "Use baseline as the control. Any extra context, evidence, or token cost in the other branches should earn its place by improving the response."
            )

    if "engram" in names:
        lessons.append(
            "For the memory branch, check whether the retrieved memories are relevant, recent enough, and actually reflected in the final answer."
        )

    if "rag" in names:
        lessons.append(
            "For the retrieval branch, check whether the included documents answer the user question more directly than the model could on its own."
        )

    if not lessons:
        lessons.append(
            "Compare these runs by asking what changed in the prompt, what evidence was added, and whether the added complexity improved the answer."
        )

    return lessons


def describe_compare_group_for_beginners(runs: list[RunArtifact]) -> list[str]:
    names = [run.augmenter_id for run in runs]
    steps = [
        "Start with the Response tab and decide which answer you trust most before you look at the internal details.",
        "Then open Prompt to see the exact text that was sent to the model. This is the best way to see what changed between branches.",
        "Use Token accounting to ask whether the extra context made the run more expensive.",
    ]

    if "baseline" in names and len(names) > 1:
        steps.insert(
            1,
            "Treat baseline as the control branch. The other branches only help if they improve the answer enough to justify the extra complexity.",
        )

    if any(name in names for name in ("engram_lite", "engram", "rag")):
        steps.append(
            "Use Evidence and Retrieval to see whether the added support is relevant and whether the answer actually used it."
        )

    if "rag" in names:
        steps.append(
            "If the RAG branch wins, try to explain which document or retrieval step made the difference."
        )

    if "engram" in names:
        steps.append(
            "If the memory branch wins, try to point to the specific memory that changed the answer."
        )

    return steps


def describe_run_for_teaching(run: RunArtifact) -> str:
    label = _AUGMENTER_LABELS.get(run.augmenter_id, f"{run.augmenter_id} branch")
    evidence_count = len(get_evidence(run.trace))
    retrieval_count = _nonempty_int(get_retrieval_summary(run.trace).get("selected_count"))
    token_total = _nonempty_int(get_token_accounting(run.trace).get("total_tokens"))

    parts = [f"This {label} shows what changed when `{run.augmenter_id}` was active."]
    if evidence_count:
        parts.append(f"It surfaced {evidence_count} evidence item{'s' if evidence_count != 1 else ''} for inspection.")
    if retrieval_count:
        parts.append(f"The retrieval stage selected {retrieval_count} document{'s' if retrieval_count != 1 else ''}.")
    if token_total is not None:
        parts.append(f"The assembled prompt used {token_total} total tokens.")
    return " ".join(parts)


def describe_run_for_beginners(run: RunArtifact) -> str:
    branch_name = {
        "baseline": "baseline branch",
        "engram_lite": "lightweight memory branch",
        "engram": "advanced memory branch",
        "rag": "retrieval branch",
    }.get(run.augmenter_id, f"{run.augmenter_id} branch")

    if run.status == "skipped":
        return f"This {branch_name} did not run, so compare the branches that produced actual results."
    if run.error:
        return f"This {branch_name} hit an error. For a beginner, that means you should not compare its answer quality until the infrastructure problem is fixed."

    evidence_count = len(get_evidence(run.trace))
    retrieval_count = _nonempty_int(get_retrieval_summary(run.trace).get("selected_count"))
    token_total = _nonempty_int(get_token_accounting(run.trace).get("total_tokens"))

    if run.augmenter_id == "baseline":
        opening = "This baseline branch is the control case. Use it to judge whether added memory or retrieval actually helped."
    elif run.augmenter_id == "engram":
        opening = "This memory branch tries to improve the answer by adding stored context from earlier interactions or saved memory."
    elif run.augmenter_id == "rag":
        opening = "This retrieval branch tries to improve the answer by pulling in outside documents or records before the model responds."
    else:
        opening = f"This {branch_name} shows how the system behaved with `{run.augmenter_id}` enabled."

    parts = [opening]
    if evidence_count:
        parts.append(f"You can inspect {evidence_count} evidence item{'s' if evidence_count != 1 else ''} to see what support the branch exposed.")
    if retrieval_count:
        parts.append(f"It selected {retrieval_count} document{'s' if retrieval_count != 1 else ''} during retrieval.")
    if token_total is not None:
        parts.append(f"The final prompt used {token_total} tokens, which gives you a rough cost signal.")
    return " ".join(parts)


def explain_prompt_tab(trace: Any) -> str:
    sections = get_sections(trace)
    accounting = get_token_accounting(trace)
    total = _nonempty_int(accounting.get("total_tokens"))
    compressed = bool(accounting.get("compressed"))
    truncated = bool(accounting.get("truncated"))

    if sections:
        message = "Read this tab as the actual context sent to the model, not just a debug artifact."
    else:
        message = "Use this tab to verify what text actually reached the model."

    if total is not None:
        message += f" The current assembled prompt is {total} tokens."
    if compressed:
        message += " Compression was applied, so some context may have been shortened before inference."
    if truncated:
        message += " Truncation occurred, so some candidate context did not fit into the final window."
    return message


def explain_prompt_tab_for_beginners(trace: Any) -> str:
    accounting = get_token_accounting(trace)
    total = _nonempty_int(accounting.get("total_tokens"))
    compressed = bool(accounting.get("compressed"))
    truncated = bool(accounting.get("truncated"))

    message = "This is the exact text the model saw before it answered. When two branches behave differently, this tab usually shows why."
    if total is not None:
        message += f" This prompt used {total} tokens."
    if compressed:
        message += " Some context was compressed, so the model may have seen a shorter version of the original material."
    if truncated:
        message += " Some candidate context did not fit, so the model did not get everything the pipeline considered."
    return message


def explain_token_tab_for_beginners(trace: Any) -> str:
    accounting = get_token_accounting(trace)
    total = _nonempty_int(accounting.get("total_tokens"))
    if total is None:
        return "Use token accounting as a rough cost meter. More tokens usually mean more context, more latency, and more opportunity for distraction."
    return f"Use token accounting as a rough cost meter. This branch used {total} tokens, so ask whether the extra context was worth the extra cost."


def explain_evidence_tab(trace: Any) -> str:
    evidence = get_evidence(trace)
    if not evidence:
        return "No explicit evidence was attached to this run. That is acceptable for a control branch, but an augmented branch should justify why no inspectable support was retained."
    return (
        f"These {len(evidence)} evidence item{'s' if len(evidence) != 1 else ''} are the support the pipeline chose to expose. "
        "Ask whether each item is relevant, whether anything important is missing, and whether the final answer actually uses this support."
    )


def explain_evidence_tab_for_beginners(trace: Any) -> str:
    evidence = get_evidence(trace)
    if not evidence:
        return "No evidence is shown here. That can be normal for a baseline run, but it is a warning sign if an augmented branch claims to use extra support without exposing any."
    return (
        f"These {len(evidence)} evidence item{'s' if len(evidence) != 1 else ''} are the pieces of support you can actually inspect. "
        "Ask two simple questions: are they relevant, and does the final answer seem to use them?"
    )


def explain_retrieval_tab(trace: Any) -> str:
    summary = get_retrieval_summary(trace)
    events = get_retrieval_events(trace)
    selected = _nonempty_int(summary.get("selected_count"))

    if not summary and not events:
        return "No retrieval diagnostics were recorded for this run. Treat that as a signal that this branch either skipped retrieval or did not expose enough telemetry to teach from."

    message = "Use this tab to inspect retrieval as a process, not as a black box."
    if selected is not None:
        message += f" The pipeline selected {selected} document{'s' if selected != 1 else ''} for the final context."
    if events:
        message += f" {len(events)} retrieval-stage event{'s' if len(events) != 1 else ''} were captured, which helps show where filtering or reranking occurred."
    return message


def explain_retrieval_tab_for_beginners(trace: Any) -> str:
    summary = get_retrieval_summary(trace)
    events = get_retrieval_events(trace)
    selected = _nonempty_int(summary.get("selected_count"))

    if not summary and not events:
        return "No retrieval details were recorded for this run. That usually means retrieval was skipped or the branch did not expose enough information to teach from."

    message = "This tab shows how the system chose outside material before answering."
    if selected is not None:
        message += f" It kept {selected} document{'s' if selected != 1 else ''} in the final context."
    if events:
        message += f" You can also inspect {len(events)} retrieval event{'s' if len(events) != 1 else ''} to see where filtering or reranking happened."
    message += " When a retrieval branch improves the answer, this tab helps you explain why."
    return message


def explain_agent_tab(trace: Any) -> str:
    summary = get_agent_summary(trace)
    exec_summary = get_agent_execution_summary(trace)
    blocked = int(exec_summary.get("blocked_count", 0) or 0)
    degraded = int(exec_summary.get("degraded_count", 0) or 0)
    approvals = int(exec_summary.get("approval_count", 0) or 0)

    if not summary and blocked == 0 and degraded == 0 and approvals == 0:
        return "No agent diagnostics were recorded for this run. That usually means this branch did not execute agent-style planning or tool activity."

    message = "Read agent traces in terms of safety and control, not just success."
    if approvals:
        message += f" {approvals} step{'s' if approvals != 1 else ''} required approval."
    if blocked:
        message += f" {blocked} step{'s' if blocked != 1 else ''} {'was' if blocked == 1 else 'were'} blocked by policy or runtime constraints."
    if degraded:
        message += f" {degraded} step{'s' if degraded != 1 else ''} {'ran' if degraded != 1 else 'ran'} in a degraded mode, which is useful for teaching fallback behavior but should not be mistaken for full isolation."
    return message


def explain_agent_tab_for_beginners(trace: Any) -> str:
    summary = get_agent_summary(trace)
    exec_summary = get_agent_execution_summary(trace)
    blocked = int(exec_summary.get("blocked_count", 0) or 0)
    degraded = int(exec_summary.get("degraded_count", 0) or 0)
    approvals = int(exec_summary.get("approval_count", 0) or 0)

    if not summary and blocked == 0 and degraded == 0 and approvals == 0:
        return "No agent activity was recorded here. That usually means this run did not do planning or tool use."

    message = "Use this tab to separate 'the agent got something done' from 'the agent behaved safely and predictably.'"
    if approvals:
        message += f" {approvals} step{'s' if approvals != 1 else ''} required approval before continuing."
    if blocked:
        message += f" {blocked} step{'s' if blocked != 1 else ''} {'was' if blocked == 1 else 'were'} blocked."
    if degraded:
        message += f" {degraded} step{'s' if degraded != 1 else ''} {'used' if degraded == 1 else 'used'} a degraded or fallback path."
    message += " Blocked or degraded steps are safety signals, but they are not proof that the runtime had hard isolation."
    return message


def explain_readiness_for_teaching(*, status: str, exists: bool, reachable: bool | None, models_available: bool | None) -> str:
    if not exists:
        return "The engine is not registered, so the workbench cannot yet demonstrate model behavior through the shared engine layer."
    if reachable is False:
        return "The engine is configured but unreachable. For teaching, this means learners are blocked before they reach memory or retrieval concepts, so engine setup must be fixed first."
    if models_available is False:
        return "The engine is reachable but no models are visible. That is a useful distinction to teach: backend connectivity and model availability are separate concerns."
    if status == "ok":
        return "The engine is ready. This is the point where students can start comparing baseline, memory, and retrieval runs instead of troubleshooting infrastructure."
    return "The engine is partially configured. Use the health details and visible models to identify whether the problem is registration, connectivity, or missing model inventory."


def explain_readiness_for_beginners(*, status: str, exists: bool, reachable: bool | None, models_available: bool | None) -> str:
    if not exists:
        return "The UI does not know about this engine yet. Before you study memory or retrieval, register the engine so the workbench can send model calls through the shared interface."
    if reachable is False:
        return "The engine is listed, but the UI cannot reach it. Fix the backend connection first; otherwise later teaching steps will fail for infrastructure reasons instead of conceptual ones."
    if models_available is False:
        return "The backend is reachable, but no models are available to run. That means connectivity is partly working, but the actual model inventory still needs attention."
    if status == "ok":
        return "The engine is ready. This is the point where a beginner can stop debugging setup and start learning from actual comparison runs."
    return "The engine is only partly ready. Use the health details to decide whether the missing piece is registration, reachability, or model availability."


def describe_readiness_steps_for_beginners(*, status: str, exists: bool, reachable: bool | None, models_available: bool | None) -> list[str]:
    if not exists:
        return [
            "Pick a registered engine or connect the UI to the llm_engines registry.",
            "Refresh readiness after registration.",
            "Only move on to comparison runs once the engine appears in the workbench.",
        ]
    if reachable is False:
        return [
            "Start the backend service or correct the connection settings.",
            "Refresh readiness and recheck the health details.",
            "Do not debug memory or retrieval yet, because the model call itself is still blocked.",
        ]
    if models_available is False:
        return [
            "Provision, download, or register at least one model for this engine.",
            "Use the Models view to confirm that the UI can see it.",
            "Then return to Compare or Single run and execute a simple baseline call.",
        ]
    if status == "ok":
        return [
            "Run a simple baseline prompt first.",
            "Then compare baseline against memory or retrieval.",
            "Use the Prompt, Evidence, and Token tabs to explain what changed.",
        ]
    return [
        "Open the health details and identify which readiness signal is still incomplete.",
        "Check whether the issue is registration, connectivity, or model inventory.",
        "Refresh readiness after each fix instead of changing multiple variables at once.",
    ]
