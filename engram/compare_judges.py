"""
Engram Memory Eval — Judge Comparison

Runs Claude and a local Ollama model as judges on the same retrievals
and reports per-field agreement rates.

Usage:
    python compare_judges.py tests/eval/results/ \
        --trial 0 \
        --local-model qwen3:32b \
        --ollama-url http://localhost:11434

Requires the trial JSON to already exist (run at least trial 0 first).
Reads retrievals from the trial file, re-judges with both models,
then computes field-level agreement.
"""
import asyncio
import aiohttp
import json
import os
import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Shared judge prompt (identical for both models) ───────────────────────────

JUDGE_SYSTEM = """
You are a strict memory retrieval judge. Given a query, the expected fact,
and a list of retrieved context chunks, you evaluate whether the retrieval
succeeded. Output ONLY a JSON object. No commentary, no markdown fences.
"""

JUDGE_PROMPT = """
EXPECTED FACT:
{canonical}

EXPECTED SNIPPET (must appear conceptually in correct result):
{expected_snippet}

QUERY ISSUED:
{query}

QUERY TYPE: {query_type}
(If query_type is "decoy", the expected fact should NOT be retrieved — mark retrieved=false if it does appear.)

RETRIEVED CONTEXT CHUNKS:
{chunks}

Evaluate and return this JSON object:
{{
  "retrieved": true|false,
  "relevance": 0-5,
  "contaminated": true|false,
  "verbatim_match": true|false,
  "notes": "one sentence explanation"
}}

Definitions:
- retrieved: the expected fact (or its core claim) is present in the chunks
- relevance: 0=wrong topic, 5=exact match
- contaminated: a clearly wrong/contradicting fact was returned
- verbatim_match: the expected_snippet appears nearly verbatim in the chunks
- For decoy queries: retrieved should be FALSE if the target fact is absent (correct behavior)
"""

FIELDS = ["retrieved", "contaminated", "verbatim_match"]  # bool fields to compare
# relevance is ordinal — track mean absolute error separately


@dataclass
class Judgment:
    retrieved: bool
    relevance: int
    contaminated: bool
    verbatim_match: bool
    notes: str
    model: str
    parse_error: Optional[str] = None


# ── Claude judge ──────────────────────────────────────────────────────────────

class ClaudeJudge:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_lock = asyncio.Lock()
        self._rate_interval = 1.3
        self._last_call_time = 0.0

    async def start(self):
        self._session = aiohttp.ClientSession()

    async def stop(self):
        if self._session:
            await self._session.close()

    async def judge(self, prompt: str) -> Judgment:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        payload = {
            "model": self.model,
            "max_tokens": 512,
            "system": JUDGE_SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        async with self._rate_lock:
            now = time.monotonic()
            wait = self._rate_interval - (now - self._last_call_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call_time = time.monotonic()
            try:
                async with self._session.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()
                    if "content" not in data:
                        return _error_judgment(self.model, f"API error: {data.get('error')}")
                    return _parse(data["content"][0]["text"], self.model)
            except Exception as e:
                return _error_judgment(self.model, str(e))


# ── Ollama judge ──────────────────────────────────────────────────────────────

class OllamaJudge:
    def __init__(self, model: str = "qwen3:32b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        # No rate limit needed for local model
        self._sem = asyncio.Semaphore(1)  # one at a time to avoid VRAM thrash

    async def start(self):
        self._session = aiohttp.ClientSession()

    async def stop(self):
        if self._session:
            await self._session.close()

    async def judge(self, prompt: str) -> Judgment:
        full_prompt = f"{JUDGE_SYSTEM.strip()}\n\n{prompt}"
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.1},  # low temp for deterministic JSON
        }
        async with self._sem:
            try:
                async with self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    data = await resp.json()
                    raw = data.get("response", "")
                    return _parse(raw, self.model)
            except Exception as e:
                return _error_judgment(self.model, str(e))


# ── Shared helpers ────────────────────────────────────────────────────────────

def _parse(text: str, model: str) -> Judgment:
    text = text.strip()
    # Strip markdown fences if present
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    # Some models wrap in <think>...</think>; strip it
    if "<think>" in text:
        text = text[text.rfind("</think>") + 8:].strip()
    try:
        d = json.loads(text)
        return Judgment(
            retrieved=bool(d.get("retrieved", False)),
            relevance=int(d.get("relevance", 0)),
            contaminated=bool(d.get("contaminated", False)),
            verbatim_match=bool(d.get("verbatim_match", False)),
            notes=str(d.get("notes", "")),
            model=model,
        )
    except (json.JSONDecodeError, ValueError) as e:
        return _error_judgment(model, f"parse error: {e} | raw: {text[:200]}")


def _error_judgment(model: str, error: str) -> Judgment:
    return Judgment(
        retrieved=False, relevance=0, contaminated=False,
        verbatim_match=False, notes="", model=model, parse_error=error,
    )


def _build_prompt(j: dict, corpus: dict) -> str:
    fact = corpus.get(j["fact_id"], {})
    chunks = "\n---\n".join(j.get("retrieved_chunks", [])) or "(no chunks returned)"
    return JUDGE_PROMPT.format(
        canonical=fact.get("canonical", ""),
        expected_snippet=fact.get("expected_snippet", ""),
        query=j.get("query", ""),
        query_type=j.get("query_type", ""),
        chunks=chunks,
    )


# ── Comparison runner ─────────────────────────────────────────────────────────

async def run_comparison(
    trial_path: Path,
    corpus: dict,
    claude_judge: ClaudeJudge,
    ollama_judge: OllamaJudge,
    max_samples: Optional[int] = None,
) -> dict:
    trial = json.loads(trial_path.read_text())
    judgments = trial["judgment_results"]

    # We need the original retrieval chunks — stored in judgment_results
    # (they were saved by trial_runner). If not present, bail early.
    sample = judgments[0] if judgments else {}
    if "retrieved_chunks" not in sample:
        print("[compare] WARNING: retrieved_chunks not in judgment_results.")
        print("  Re-run trial_runner.py with a version that saves chunks,")
        print("  or set SAVE_CHUNKS=True in trial_runner.py.")
        return {}

    if max_samples:
        judgments = judgments[:max_samples]

    print(f"[compare] {len(judgments)} judgments to re-judge with both models")

    # Build prompts
    prompts = [_build_prompt(j, corpus) for j in judgments]

    # Run both judges concurrently (Claude rate-limited, Ollama semaphore-limited)
    print("[compare] Sending to Claude and Ollama simultaneously...")
    claude_tasks = [claude_judge.judge(p) for p in prompts]
    ollama_tasks = [ollama_judge.judge(p) for p in prompts]
    claude_results, ollama_results = await asyncio.gather(
        asyncio.gather(*claude_tasks),
        asyncio.gather(*ollama_tasks),
    )

    # Compute agreement
    n = len(judgments)
    agreement = {f: 0 for f in FIELDS}
    relevance_abs_errors = []
    claude_errors = 0
    ollama_errors = 0
    disagreements = []

    for orig, cr, olr in zip(judgments, claude_results, ollama_results):
        if cr.parse_error:
            claude_errors += 1
        if olr.parse_error:
            ollama_errors += 1

        for field in FIELDS:
            cv = getattr(cr, field)
            ov = getattr(olr, field)
            if cv == ov:
                agreement[field] += 1
            else:
                disagreements.append({
                    "fact_id": orig["fact_id"],
                    "query_type": orig["query_type"],
                    "field": field,
                    "claude": cv,
                    "ollama": ov,
                    "claude_notes": cr.notes,
                    "ollama_notes": olr.notes,
                })

        if not cr.parse_error and not olr.parse_error:
            relevance_abs_errors.append(abs(cr.relevance - olr.relevance))

    agreement_rates = {f: agreement[f] / n for f in FIELDS}
    mean_relevance_error = (
        sum(relevance_abs_errors) / len(relevance_abs_errors)
        if relevance_abs_errors else None
    )

    return {
        "trial_label": trial["label"],
        "n_samples": n,
        "claude_parse_errors": claude_errors,
        "ollama_parse_errors": ollama_errors,
        "agreement_rates": agreement_rates,
        "mean_relevance_abs_error": mean_relevance_error,
        "disagreements": disagreements,
    }


def print_report(result: dict, ollama_model: str):
    if not result:
        return
    print(f"\n{'='*60}")
    print(f"Judge Comparison Report — Trial: {result['trial_label']}")
    print(f"n={result['n_samples']}  "
          f"claude_errors={result['claude_parse_errors']}  "
          f"ollama_errors={result['ollama_parse_errors']}")
    print(f"{'='*60}")
    print(f"\nField agreement rates (Claude vs {ollama_model}):")
    for field, rate in result["agreement_rates"].items():
        bar = "█" * int(rate * 20)
        print(f"  {field:<20} {rate:>6.1%}  {bar}")
    mae = result.get("mean_relevance_abs_error")
    if mae is not None:
        print(f"  {'relevance (MAE)':<20} {mae:>6.2f}  (0=perfect, 5=max)")

    disagreements = result.get("disagreements", [])
    print(f"\nDisagreements: {len(disagreements)} of {result['n_samples']} judgments")

    # Break down by field
    by_field = {}
    for d in disagreements:
        by_field.setdefault(d["field"], []).append(d)

    for field, cases in by_field.items():
        print(f"\n  {field} disagreements ({len(cases)}):")
        # Show first 5
        for c in cases[:5]:
            print(f"    [{c['query_type']}] {c['fact_id']}")
            print(f"      Claude: {c['claude']}  — {c['claude_notes'][:80]}")
            print(f"      Ollama: {c['ollama']}  — {c['ollama_notes'][:80]}")
        if len(cases) > 5:
            print(f"    ... and {len(cases) - 5} more")

    # Practical recommendation
    print(f"\n{'='*60}")
    r_rate = result["agreement_rates"].get("retrieved", 0)
    c_rate = result["agreement_rates"].get("contaminated", 0)
    print("Recommendation:")
    if r_rate >= 0.95 and c_rate >= 0.90:
        print(f"  {ollama_model} is a suitable drop-in judge.")
        print("  Agreement is high enough that noise won't distort trends.")
    elif r_rate >= 0.90:
        print(f"  {ollama_model} is acceptable for recall metrics.")
        print("  Use Claude for contamination/contradiction analysis.")
    else:
        print(f"  {ollama_model} shows significant disagreement.")
        print("  Consider a larger model or stick with Claude.")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", nargs="?", default="tests/eval/results")
    parser.add_argument("--trial", type=int, default=0)
    parser.add_argument("--local-model", default="qwen3:32b")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--samples", type=int, default=None,
                        help="Limit to N judgments (default: all)")
    parser.add_argument("--save", action="store_true",
                        help="Save comparison results to JSON")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    trial_path = next(
        (p for p in sorted(results_dir.glob("trial_*.json"))
         if f"_{args.trial:02d}_" in p.name or p.name.startswith(f"trial_{args.trial:02d}_")),
        None
    )
    if trial_path is None:
        print(f"Trial {args.trial} not found in {results_dir}")
        return

    corpus_path = Path("tests/eval/eval_corpus.json")
    corpus = {f["id"]: f for f in json.loads(corpus_path.read_text())}

    claude = ClaudeJudge()
    ollama = OllamaJudge(model=args.local_model, base_url=args.ollama_url)

    await claude.start()
    await ollama.start()
    try:
        result = await run_comparison(
            trial_path, corpus, claude, ollama, max_samples=args.samples
        )
        print_report(result, args.local_model)
        if args.save and result:
            out = results_dir / f"judge_comparison_trial{args.trial}.json"
            out.write_text(json.dumps(result, indent=2))
            print(f"\nSaved to {out}")
    finally:
        await claude.stop()
        await ollama.stop()


if __name__ == "__main__":
    asyncio.run(main())
