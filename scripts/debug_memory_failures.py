#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


def _add_repo_paths(repo_root: Path) -> None:
    candidates = [
        repo_root,
        repo_root / "engram",
        repo_root / "llm_engines",
        repo_root / "llm_inspector",
        repo_root / "llm_inspector_ui",
        repo_root / "rag_lib",
        repo_root / "agent_lib",
        repo_root / "llm_harness_core",
        repo_root / "language_tutor",
    ]
    seen = set()
    for path in candidates:
        if path.exists():
            s = str(path)
            if s not in seen:
                sys.path.insert(0, s)
                seen.add(s)


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_memory_eval(repo_root: Path):
    module_path = repo_root / "integration_tests" / "memory_eval.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Could not find {module_path}")
    return _load_module(module_path, "memory_eval_runtime")


def _safe_text(item: Any) -> str:
    for attr in ("text", "content", "message", "value"):
        if hasattr(item, attr):
            try:
                value = getattr(item, attr)
                if isinstance(value, str) and value.strip():
                    return value
            except Exception:
                pass
    if isinstance(item, dict):
        for key in ("text", "content", "message", "value", "summary", "detail"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return str(item)


def _to_serializable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_serializable(v) for v in obj]
    if hasattr(obj, "to_dict"):
        try:
            return _to_serializable(obj.to_dict())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return {k: _to_serializable(v) for k, v in vars(obj).items()}
        except Exception:
            pass
    return str(obj)


def _layer_items(memory_eval, context: Any) -> dict[str, list[str]]:
    return memory_eval._collect_layer_items(context)  # type: ignore[attr-defined]


def _score_probe(memory_eval, text: str, probe: Any) -> dict[str, Any]:
    return memory_eval._score_text_against_probe(text, probe)  # type: ignore[attr-defined]


def _get_probe_names_from_report(report_path: Path, backend: str, scenario: str) -> list[str]:
    data = json.loads(report_path.read_text(encoding="utf-8"))

    if "results" in data:
        scenario_name = scenario if scenario.endswith("_memory_quality") else f"{scenario}_memory_quality"
        scenario_map = data["results"]
        if scenario_name not in scenario_map:
            raise KeyError(f"Scenario '{scenario_name}' not found in report. Available: {', '.join(sorted(scenario_map))}")
        backend_data = scenario_map[scenario_name]["backends"][backend]
        return list(backend_data["summary"].get("failed_probes", []))

    if "backends" in data:
        report_scenario_name = data.get("scenario", {}).get("name")
        scenario_name = scenario if scenario.endswith("_memory_quality") else f"{scenario}_memory_quality"
        if report_scenario_name and scenario_name != report_scenario_name:
            raise KeyError(f"Report contains scenario '{report_scenario_name}', not '{scenario_name}'")
        backend_data = data["backends"][backend]
        return list(backend_data["summary"].get("failed_probes", []))

    raise ValueError(f"Unrecognized report structure in {report_path}")


def _find_probe(resolved_scenario: Any, name: str) -> Any:
    for probe in resolved_scenario.probes:
        if probe.name == name:
            return probe
    raise KeyError(f"Unknown probe '{name}' for scenario '{resolved_scenario.name}'")


def _episodic_dump(memory: Any, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        items = memory.search_episodes("", n=limit)
    except Exception:
        return rows

    for item in items:
        rows.append(
            {
                "id": getattr(item, "id", None),
                "text": _safe_text(item),
                "importance": getattr(item, "importance", None),
                "timestamp": getattr(item, "timestamp", None),
                "metadata": _to_serializable(getattr(item, "metadata", None)),
            }
        )
    return rows


def _semantic_dump(memory: Any, limit: int) -> dict[str, Any]:
    semantic = getattr(memory, "semantic", None)
    if semantic is None:
        return {"facts": [], "preferences": []}

    out: dict[str, Any] = {"facts": [], "preferences": []}
    if hasattr(semantic, "list_facts"):
        try:
            out["facts"] = _to_serializable(semantic.list_facts(limit=limit))
        except Exception as exc:
            out["facts_error"] = str(exc)
    if hasattr(semantic, "list_preferences"):
        try:
            out["preferences"] = _to_serializable(semantic.list_preferences(limit=limit))
        except Exception as exc:
            out["preferences_error"] = str(exc)
    return out


def _trace_dump(memory: Any, probe: Any) -> dict[str, Any] | None:
    if not hasattr(memory, "build_prompt_trace"):
        return None
    question = probe.question or "probe"
    try:
        trace = memory.build_prompt_trace(question, query=probe.query)
    except Exception as exc:
        return {"trace_error": str(exc)}
    return _to_serializable(trace)


def _direct_search_dump(memory: Any, probe: Any, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not hasattr(memory, "search_episodes"):
        return rows
    try:
        items = memory.search_episodes(probe.query, n=limit)
    except Exception as exc:
        return [{"error": str(exc)}]
    for item in items:
        rows.append(
            {
                "id": getattr(item, "id", None),
                "text": _safe_text(item),
                "importance": getattr(item, "importance", None),
                "score": getattr(item, "score", None),
                "metadata": _to_serializable(getattr(item, "metadata", None)),
            }
        )
    return rows


def _run_diagnostic(repo_root: Path, backend: str, scenario: str, probe_names: list[str], dump_limit: int) -> dict[str, Any]:
    _add_repo_paths(repo_root)
    memory_eval = _load_memory_eval(repo_root)
    resolved_scenario = memory_eval._resolve_scenario(scenario)  # type: ignore[attr-defined]

    adapters = {
        "engram": memory_eval.EngramAdapter,
    }
    if backend not in adapters:
        raise KeyError(f"Unknown backend '{backend}'. Expected one of: {', '.join(sorted(adapters))}")

    adapter_cls = adapters[backend]

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        adapter = adapter_cls(root / backend)
        seed_stats = None
        try:
            for turn in resolved_scenario.seed_turns:
                adapter.seed_turn(turn)
            adapter.flush()
            seed_stats = adapter.get_stats()
        finally:
            adapter.close()

        cold_adapter = adapter.reopen_cold()
        try:
            cold_adapter.flush()
            cold_stats = cold_adapter.get_stats()
            memory = getattr(cold_adapter, "memory", None)

            data: dict[str, Any] = {
                "backend": backend,
                "scenario": resolved_scenario.name,
                "seed_stats": _to_serializable(seed_stats),
                "cold_stats": _to_serializable(cold_stats),
                "stored_memory": {
                    "episodic": _episodic_dump(memory, dump_limit) if memory is not None else [],
                    "semantic": _semantic_dump(memory, dump_limit) if memory is not None else {"facts": [], "preferences": []},
                },
                "probes": [],
            }

            for probe_name in probe_names:
                probe = _find_probe(resolved_scenario, probe_name)
                eval_result = memory_eval.evaluate_probe(cold_adapter, probe)  # type: ignore[attr-defined]
                context = cold_adapter.get_context(probe.query)
                layers = _layer_items(memory_eval, context)
                prompt_result = cold_adapter.build_prompt(probe.question or "probe", query=probe.query)
                prompt_text = str(prompt_result.get("prompt", ""))

                probe_entry = {
                    "probe": probe.name,
                    "category": probe.category,
                    "query": probe.query,
                    "question": probe.question,
                    "notes": probe.notes,
                    "eval_result": _to_serializable(eval_result),
                    "retrieved_layers": layers,
                    "direct_episode_search": _direct_search_dump(memory, probe, dump_limit) if memory is not None else [],
                    "prompt_support": _score_probe(memory_eval, prompt_text, probe),
                    "prompt_result": {
                        "prompt_tokens": int(prompt_result.get("prompt_tokens", 0) or 0),
                        "memory_tokens": int(prompt_result.get("memory_tokens", 0) or 0),
                        "compressed": bool(prompt_result.get("compressed", False)),
                        "prompt": prompt_text,
                    },
                    "trace": _trace_dump(memory, probe) if memory is not None else None,
                }
                data["probes"].append(probe_entry)
            return data
        finally:
            cold_adapter.close()


def _markdown_report(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Memory Diagnostic: {data['backend']} / {data['scenario']}")
    lines.append("")
    lines.append("## Stats")
    lines.append("")
    lines.append("### Seed stats")
    lines.append("```json")
    lines.append(json.dumps(data.get("seed_stats", {}), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("### Cold stats")
    lines.append("```json")
    lines.append(json.dumps(data.get("cold_stats", {}), indent=2))
    lines.append("```")
    lines.append("")

    stored = data.get("stored_memory", {})
    lines.append("## Stored memory snapshot")
    lines.append("")
    lines.append("### Episodic")
    lines.append("```json")
    lines.append(json.dumps(stored.get("episodic", []), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("### Semantic")
    lines.append("```json")
    lines.append(json.dumps(stored.get("semantic", {}), indent=2))
    lines.append("```")
    lines.append("")

    for probe in data.get("probes", []):
        lines.append(f"## Probe: {probe['probe']}")
        lines.append("")
        lines.append(f"- Category: `{probe.get('category')}`")
        lines.append(f"- Query: `{probe.get('query')}`")
        if probe.get("question"):
            lines.append(f"- Question: `{probe.get('question')}`")
        if probe.get("notes"):
            lines.append(f"- Notes: {probe.get('notes')}")
        lines.append("")
        lines.append("### Evaluation result")
        lines.append("```json")
        lines.append(json.dumps(probe.get("eval_result", {}), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### Retrieved layers")
        lines.append("```json")
        lines.append(json.dumps(probe.get("retrieved_layers", {}), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### Direct episodic search")
        lines.append("```json")
        lines.append(json.dumps(probe.get("direct_episode_search", []), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### Prompt support")
        lines.append("```json")
        lines.append(json.dumps(probe.get("prompt_support", {}), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### Prompt result")
        lines.append("```json")
        lines.append(json.dumps(probe.get("prompt_result", {}), indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### Prompt trace")
        lines.append("```json")
        lines.append(json.dumps(probe.get("trace", {}), indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose failed engram memory probes by printing stored memory, retrieved candidates, prompt assembly, and trace output."
    )
    parser.add_argument("--repo-root", default=".", help="Path to the ai_tools repo root.")
    parser.add_argument("--backend", default="engram", choices=("engram"))
    parser.add_argument("--scenario", default="stress", choices=("default", "stress"))
    parser.add_argument(
        "--probe",
        action="append",
        default=[],
        help="Probe name to inspect. Can be provided multiple times.",
    )
    parser.add_argument(
        "--report-json",
        help="Optional memory_eval_report.json. If provided and --probe is omitted, inspect the failed probes for the selected backend and scenario.",
    )
    parser.add_argument("--dump-limit", type=int, default=10, help="Maximum stored/search items to dump per section.")
    parser.add_argument("--json-out", default="memory_diagnostic.json", help="Output JSON file.")
    parser.add_argument("--markdown-out", default="memory_diagnostic.md", help="Output Markdown file.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    probe_names = list(args.probe)

    if not probe_names and args.report_json:
        probe_names = _get_probe_names_from_report(Path(args.report_json).resolve(), args.backend, args.scenario)

    if not probe_names:
        print(
            "No probes selected. Provide --probe NAME (multiple allowed), or --report-json memory_eval_report.json to auto-select failed probes.",
            file=sys.stderr,
        )
        return 2

    data = _run_diagnostic(
        repo_root=repo_root,
        backend=args.backend,
        scenario=args.scenario,
        probe_names=probe_names,
        dump_limit=args.dump_limit,
    )

    json_out = Path(args.json_out).resolve()
    md_out = Path(args.markdown_out).resolve()
    json_out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_out.write_text(_markdown_report(data), encoding="utf-8")

    print(f"Wrote {json_out}")
    print(f"Wrote {md_out}")
    print("")
    print(f"Backend: {data['backend']}")
    print(f"Scenario: {data['scenario']}")
    print(f"Probes: {', '.join(probe_names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
