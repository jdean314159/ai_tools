from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path
import logging
logging.getLogger("engram").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)

from llm_inspector.adapters import AdapterRegistry, AdapterSpec
from llm_inspector.export import bundle_to_json, diff_to_json, report_to_json
from llm_inspector.inspectors import ContextInspector
from llm_inspector.inspectors.bundle import build_bundle
from llm_inspector.inspectors.diff import diff_traces
from llm_inspector.renderers import render_comparison
from llm_inspector.renderers.diff_console import render_diff
from llm_inspector.artifacts import (
    artifact_comparison_to_dict,
    artifact_inspection_to_dict,
    compare_artifact_files,
    inspect_artifact_path,
    render_artifact_comparison,
    render_artifact_inspection,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llm-inspect")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- compare ---
    cmp_p = sub.add_parser("compare", help="Compare context assembly across augmenters.")
    cmp_p.add_argument("query", help="User query / prompt text.")
    cmp_p.add_argument("--adapter", default="baseline", help="Augmenter adapter to use (default: baseline).")
    cmp_p.add_argument("--json-out", type=str, default="", help="Write report JSON to this path.")
    cmp_p.add_argument("--text-out", type=str, default="", help="Write console report to this path.")
    cmp_p.add_argument("--no-print", action="store_true", help="Do not print console output.")
    cmp_p.add_argument("--engram-base-dir", default="~/.engram/projects/default")
    cmp_p.add_argument("--engram-profile", default="default_local")
    cmp_p.add_argument("--engram-project-type", default="programming_assistant")

    # --- diff ---
    diff_p = sub.add_parser("diff", help="Diff two adapters on the same query.")
    diff_p.add_argument("query", help="User query / prompt text.")
    diff_p.add_argument("--adapter-a", default="baseline", help="Left adapter (default: baseline).")
    diff_p.add_argument("--adapter-b", default="baseline", help="Right adapter (default: baseline).")
    diff_p.add_argument("--json-out", type=str, default="", help="Write diff JSON to this path.")
    diff_p.add_argument("--text-out", type=str, default="", help="Write diff text to this path.")
    diff_p.add_argument("--no-print", action="store_true", help="Do not print diff output.")
    diff_p.add_argument("--engram-base-dir", default="~/.engram/projects/default")
    diff_p.add_argument("--engram-profile", default="default_local")
    diff_p.add_argument("--engram-project-type", default="programming_assistant")

    # --- bundle ---
    bun_p = sub.add_parser("bundle", help="Compare multiple adapters and emit a bundle JSON (report + pairwise diffs).")
    bun_p.add_argument("query", help="User query / prompt text.")
    bun_p.add_argument(
        "--adapters",
        default="baseline",
        help="Comma-separated adapter list, e.g. 'baseline,engram' or 'baseline,baseline'.",
    )
    bun_p.add_argument("--json-out", type=str, required=True, help="Write bundle JSON to this path.")
    bun_p.add_argument("--no-print", action="store_true", help="Do not print console output.")
    bun_p.add_argument("--engram-base-dir", default="~/.engram/projects/default")
    bun_p.add_argument("--engram-profile", default="default_local")
    bun_p.add_argument("--engram-project-type", default="programming_assistant")

    # --- durable run artifacts ---
    artifact_p = sub.add_parser("artifact", help="Inspect durable run artifacts.")
    artifact_sub = artifact_p.add_subparsers(dest="artifact_cmd", required=True)
    artifact_show = artifact_sub.add_parser("show", help="Validate and summarize one artifact.")
    artifact_show.add_argument("path", type=Path)
    artifact_show.add_argument("--format", choices=("text", "json"), default="text")
    artifact_compare = artifact_sub.add_parser("compare", help="Compare defensible common artifact facts.")
    artifact_compare.add_argument("left", type=Path)
    artifact_compare.add_argument("right", type=Path)
    artifact_compare.add_argument("--format", choices=("text", "json"), default="text")

    return p


def _build_registry() -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(AdapterSpec("baseline", "llm_inspector.adapters.baseline:make_baseline"))
    if importlib.util.find_spec("engram") is not None:
        reg.register(AdapterSpec("engram", "llm_inspector.adapters.engram_adapter:make_engram"))
    return reg


def _mk_adapter(reg: AdapterRegistry, adapter_name: str, *, instance_name: str, args) -> object:
    if adapter_name not in reg.available():
        raise SystemExit(f"Unknown adapter '{adapter_name}'. Available: {', '.join(reg.available())}")

    kwargs = {"_name": instance_name}
    if adapter_name == "engram":
        kwargs.update(
            base_dir=args.engram_base_dir,
            profile=args.engram_profile,
            project_type=args.engram_project_type,
        )
    return reg.create(adapter_name, **kwargs)


def _parse_adapter_list(spec: str) -> list[str]:
    items = [s.strip() for s in (spec or "").split(",") if s.strip()]
    return items or ["baseline"]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "artifact":
        if args.artifact_cmd == "show":
            inspection = inspect_artifact_path(args.path)
            if args.format == "json":
                print(json.dumps(artifact_inspection_to_dict(inspection), indent=2, sort_keys=True))
            else:
                print(render_artifact_inspection(inspection))
            return 0
        if args.artifact_cmd == "compare":
            comparison = compare_artifact_files(args.left, args.right)
            if args.format == "json":
                print(json.dumps(artifact_comparison_to_dict(comparison), indent=2, sort_keys=True))
            else:
                print(render_artifact_comparison(comparison))
            return 0
        return 2
    reg = _build_registry()

    if args.cmd == "compare":
        aug = _mk_adapter(reg, args.adapter, instance_name=args.adapter, args=args)
        report = ContextInspector([aug]).run(args.query)
        text = render_comparison(report)

        if not args.no_print:
            print(text)

        text_out = getattr(args, "text_out", "")
        if text_out:
            Path(text_out).write_text(text, encoding="utf-8")

        json_out = getattr(args, "json_out", "")
        if json_out:
            Path(json_out).write_text(report_to_json(report), encoding="utf-8")

        return 0

    if args.cmd == "diff":
        aug_a = _mk_adapter(reg, args.adapter_a, instance_name=args.adapter_a, args=args)
        aug_b = _mk_adapter(reg, args.adapter_b, instance_name=args.adapter_b, args=args)

        ta = ContextInspector([aug_a]).run(args.query).traces[0].trace
        tb = ContextInspector([aug_b]).run(args.query).traces[0].trace

        d = diff_traces(ta, tb, name_a=args.adapter_a, name_b=args.adapter_b)
        text = render_diff(d)

        if not args.no_print:
            print(text)

        text_out = getattr(args, "text_out", "")
        if text_out:
            Path(text_out).write_text(text, encoding="utf-8")

        json_out = getattr(args, "json_out", "")
        if json_out:
            Path(json_out).write_text(diff_to_json(d), encoding="utf-8")

        return 0

    if args.cmd == "bundle":
        adapter_names = _parse_adapter_list(args.adapters)

        # Allow duplicates like "baseline,baseline" by uniquifying instance names.
        counts = Counter()
        augmenters = []
        for a in adapter_names:
            counts[a] += 1
            inst = a if counts[a] == 1 else f"{a}_{counts[a]}"
            augmenters.append(_mk_adapter(reg, a, instance_name=inst, args=args))

        report = ContextInspector(augmenters).run(args.query)
        bundle = build_bundle(report)

        Path(args.json_out).write_text(bundle_to_json(bundle), encoding="utf-8")

        if not args.no_print:
            # Print compare view (diffs are in JSON bundle)
            print(render_comparison(report))

        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
