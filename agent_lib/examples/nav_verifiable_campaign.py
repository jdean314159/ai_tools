"""Run the frozen NAV-VERIFIABLE-00 no-ledger/ledger campaign."""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from agent_lib.contracts import AgentRun, AgentTask
from agent_lib.eval.repo_navigation import (
    LlamaServerClient,
    NavigationBudget,
    NavigationPolicy,
    build_environment_manifest,
    build_navigation_harness,
    render_run_record,
    tree_content_digest,
)
from agent_lib.eval.verifiable_campaign import (
    decide_campaign,
    summarize_paired_campaign,
)
from agent_lib.eval.verifiable_navigation import (
    RELATION_CLAIMS_SCHEMA,
    PythonRelationOracle,
    RelationClaim,
    VerifiableTask,
    build_pair_manifest,
    load_verifiable_task_set,
    relation_claims_shape_error,
    score_verifiable_claims,
)


VERIFIABLE_SYSTEM_PROMPT = """You are a read-only repository navigation agent.
Use only evidence returned by tools. Return exactly one JSON object with no
surrounding text. Choose either a read_file, grep, or list_files tool action, or
return a final action with `final_output` and `relation_claims`.

Each relation claim must use the task-requested relation kind:
- definition: the exact defined symbol;
- call_edge: the syntactically direct caller in `symbol` and callee in `target`;
- call_path: the exact ordered `path_symbols`, with its first and last symbols
  repeated in `symbol` and `target`;
- mutation_target: the enclosing symbol and callable expression in `target`.

Use repository-relative paths. Cite only exact minimal syntax lines that prove
the relation. A call path needs each component call line and no surrounding
lines. For definition, use an empty `target` and empty `path_symbols`. For
call_edge and mutation_target, use empty `path_symbols`. Emit every and only
the relation kind requested by the task, and never return an empty
`relation_claims` array. Never infer runtime dispatch or invent a symbol.
Continue using tools until the requested relation is established, then
finalize."""

CAMPAIGN_RELATION_CLAIMS_SCHEMA = copy.deepcopy(RELATION_CLAIMS_SCHEMA)
CAMPAIGN_RELATION_CLAIMS_SCHEMA["minItems"] = 1


def campaign_relation_claims_shape_error(value: object) -> str | None:
    error = relation_claims_shape_error(value)
    if error:
        return error
    if not value:
        return "relation_claims must contain at least one claim"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-plan",
        type=Path,
        default=Path("agent_lib/eval_manifests/nav_verifiable_campaign_v1/run-plan.json"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model-label", default="qwen3.6:27b-q4_k_m")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--token-limit", type=int, default=120_000)
    parser.add_argument("--context-window", type=int, default=40_000)
    parser.add_argument("--minimum-output-reserve", type=int, default=512)
    parser.add_argument("--per-call-output-cap", type=int, default=2_048)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    plan_path = args.run_plan.resolve(strict=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest_dir = plan_path.parent
    campaign_manifest = json.loads(
        (manifest_dir / "campaign-admission.json").read_text(encoding="utf-8")
    )
    selected = json.loads((manifest_dir / "candidate-selection.json").read_text(encoding="utf-8"))
    selected_by_id = {str(item["task_id"]): item for item in selected["selected"]}
    tasks: list[tuple[VerifiableTask, Path]] = []
    for record in plan["task_sets"]:
        root = Path(record["source_root"]).resolve(strict=True)
        task_set = load_verifiable_task_set(
            manifest_dir / record["task_set"],
            source_root=root,
        )
        tasks.extend((task, root) for task in task_set)
    tasks.sort(key=lambda item: selected["selected_task_ids"].index(item[0].task_id))
    if args.limit is not None:
        tasks = tasks[: args.limit]

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    budget = NavigationBudget(
        cumulative_token_limit=args.token_limit,
        context_window=args.context_window,
        minimum_output_reserve=args.minimum_output_reserve,
        per_call_output_cap=args.per_call_output_cap,
    )
    client = LlamaServerClient(args.base_url, seed=args.seed)
    pairs_path = output_dir / "pairs.json"
    pairs = json.loads(pairs_path.read_text(encoding="utf-8")) if pairs_path.exists() else []
    completed_task_ids = {str(item["task_id"]) for item in pairs}
    for index, (task, root) in enumerate(tasks):
        if task.task_id in completed_task_ids:
            continue
        order = ("no_ledger", "ledger") if index % 2 == 0 else ("ledger", "no_ledger")
        shared = {
            "model_label": args.model_label,
            "seed": args.seed,
            "temperature": args.temperature,
            "max_steps": args.max_steps,
            "token_limit": args.token_limit,
            "context_window": args.context_window,
            "minimum_output_reserve": args.minimum_output_reserve,
            "per_call_output_cap": args.per_call_output_cap,
            "task_id": task.task_id,
        }
        pair_manifest = build_pair_manifest(
            pair_id=f"pair-{task.task_id}",
            task=task,
            autonomous_config={
                **shared,
                "structured_navigation": False,
                "run_label": "no_ledger",
            },
            structured_config={
                **shared,
                "structured_navigation": True,
                "run_label": "ledger",
            },
            run_order=tuple(
                "autonomous" if mode == "no_ledger" else "structured" for mode in order
            ),
        )
        pair_dir = output_dir / task.task_id
        pair_dir.mkdir(parents=True, exist_ok=True)
        (pair_dir / "pair-manifest.json").write_text(
            json.dumps(pair_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        outcomes: dict[str, dict[str, Any]] = {}
        for mode in order:
            outcome = _run_arm(
                task=task,
                root=root,
                mode=mode,
                client=client,
                budget=budget,
                args=args,
                output_path=pair_dir / f"{mode}.json",
            )
            outcomes[mode] = outcome
            print(
                json.dumps(
                    {
                        "task_id": task.task_id,
                        "tier": selected_by_id[task.task_id]["difficulty"]["tier"],
                        "mode": mode,
                        **{
                            key: outcome[key]
                            for key in (
                                "completed_with_answer",
                                "relation_correct",
                                "exact_correct",
                                "tokens",
                                "tool_steps",
                            )
                        },
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        pairs.append(
            {
                "task_id": task.task_id,
                "tier": selected_by_id[task.task_id]["difficulty"]["tier"],
                **outcomes,
            }
        )
        pairs_path.write_text(
            json.dumps(pairs, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if len(tasks) == len(selected_by_id):
        summary = summarize_paired_campaign(pairs, campaign_manifest=campaign_manifest)
        decision = decide_campaign(summary)
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "decision.json").write_text(
            json.dumps(decision, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(decision, sort_keys=True))
    return 0


def _run_arm(
    *,
    task: VerifiableTask,
    root: Path,
    mode: str,
    client: LlamaServerClient,
    budget: NavigationBudget,
    args: argparse.Namespace,
    output_path: Path,
) -> dict[str, Any]:
    ledger = mode == "ledger"
    policy = NavigationPolicy(root)
    manifest = build_environment_manifest(policy)
    oracle = PythonRelationOracle(root)
    harness = build_navigation_harness(
        root=root,
        engine=client,
        tokenizer=client,
        policy=policy,
        budget=budget,
        max_steps=args.max_steps,
        temperature=args.temperature,
        metadata={
            "eval": "NAV-VERIFIABLE-00",
            "task_id": task.task_id,
            "mode": mode,
            "seed": args.seed,
        },
        action_guard_mode="off",
        structured_navigation=ledger,
        navigation_goal_definitions=task.goal_requirements if ledger else None,
        system_prompt=VERIFIABLE_SYSTEM_PROMPT,
        final_claim_name="relation_claims",
        final_claim_schema=CAMPAIGN_RELATION_CLAIMS_SCHEMA,
        final_claim_validator=campaign_relation_claims_shape_error,
        require_observed_evidence_before_final=True,
    )
    before = tree_content_digest(root)
    try:
        run = harness.run(task.question, task_id=task.task_id)
    except Exception as exc:
        run = AgentRun(
            task=AgentTask(task_id=task.task_id, goal=task.question),
            status="error",
            stop_reason="error",
            final_output=f"{type(exc).__name__}: {exc}",
            meta={"error_type": type(exc).__name__, "error": str(exc)},
        )
    after = tree_content_digest(root)
    raw_claims = _raw_relation_claims(run)
    claims = []
    parse_errors = []
    for index, item in enumerate(raw_claims, start=1):
        if not isinstance(item, Mapping):
            parse_errors.append(f"claim {index} is not an object")
            continue
        try:
            claims.append(RelationClaim.from_mapping(item))
        except (TypeError, ValueError) as exc:
            parse_errors.append(f"claim {index}: {exc}")
    observed: dict[str, set[int]] = {}
    for call in harness.tools.telemetry.calls:
        for evidence in call.get("evidence") or []:
            observed.setdefault(str(evidence["path"]), set()).update(
                int(line) for line in evidence.get("lines") or []
            )
    score = score_verifiable_claims(
        task,
        claims,
        oracle=oracle,
        observed_lines=observed,
    )
    outcome = {
        "completed_with_answer": run.status == "completed" and bool(run.final_output.strip()),
        "relation_correct": score.relation_correct,
        "evidence_complete": score.evidence_complete,
        "evidence_precise": score.evidence_precise,
        "exact_correct": score.exact_correct and not parse_errors,
        "tokens": harness.planner.usage.cumulative_actual_tokens,
        "tool_steps": len(harness.tools.telemetry.calls),
        "status": run.status,
        "stop_reason": run.stop_reason,
        "parse_errors": parse_errors,
        "unsupported_claims": list(score.unsupported_claims),
        "incomplete_evidence_claims": list(score.incomplete_evidence_claims),
        "imprecise_claims": list(score.imprecise_claims),
        "score_errors": list(score.errors),
        "read_only_verified": before == after,
    }
    record = render_run_record(
        run=run,
        harness=harness,
        manifest=manifest,
        pre_tree_digest=before,
        post_tree_digest=after,
        score=outcome,
        config={
            "mode": mode,
            "model_label": args.model_label,
            "seed": args.seed,
            "temperature": args.temperature,
            "budget": asdict(budget),
        },
    )
    output_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return outcome


def _raw_relation_claims(run: AgentRun) -> list[Any]:
    if isinstance(run.meta.get("relation_claims"), list):
        return list(run.meta["relation_claims"])
    if run.steps and isinstance(run.steps[-1].action.meta.get("relation_claims"), list):
        return list(run.steps[-1].action.meta["relation_claims"])
    return []


if __name__ == "__main__":
    raise SystemExit(main())
