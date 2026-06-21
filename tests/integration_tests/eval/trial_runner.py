"""Execute the six-trial neural memory A/B schedule."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

try:
    from .corpus import FactCorpus
    from .engram_probe import EngramProbe
    from .eval_config import EvalConfig, TRIAL_SCHEDULE
    from .ollama_judge import OllamaJudge
except ImportError:  # Direct execution through run_eval.py.
    from corpus import FactCorpus
    from engram_probe import EngramProbe
    from eval_config import EvalConfig, TRIAL_SCHEDULE
    from ollama_judge import OllamaJudge


@dataclass
class TrialRecord:
    trial_index: int
    label: str
    subset_name: str
    repetitions: int
    distractors_injected: int
    injection_results: list[dict]
    judgment_results: list[dict]
    elapsed_sec: float
    timestamp: float
    mode: str = "retrieval"


class TrialRunner:
    def __init__(
        self,
        config: EvalConfig,
        corpus: FactCorpus,
        probe: EngramProbe,
        judge: OllamaJudge,
        output_dir: str | Path,
    ) -> None:
        self.config = config
        self.corpus = corpus
        self.probe = probe
        self.judge = judge
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[TrialRecord] = []
        self._distractor_counter = 0
        self._contradicted_ids: set[str] = set()
        self._warmup_complete = False

    async def run_all(self, resume: bool = True) -> list[TrialRecord]:
        trial_indices = {
            entry[0]: index for index, entry in enumerate(TRIAL_SCHEDULE)
        }
        for entry in self.config.schedule:
            label, subset_name, repetitions, distractors = entry
            trial_index = trial_indices[label]
            path = self.output_dir / f"trial_{trial_index:02d}_{label}.json"
            if resume and path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                saved_mode = str(raw.get("mode", "retrieval"))
                if saved_mode != self.config.mode:
                    raise ValueError(
                        "Cannot resume trial from a different evaluation mode: "
                        f"{saved_mode!r} != {self.config.mode!r}"
                    )
                known = {item.name for item in fields(TrialRecord)}
                record = TrialRecord(
                    **{key: value for key, value in raw.items() if key in known}
                )
                self.records.append(record)
                if label == "contradict":
                    self._contradicted_ids.update(
                        fact.id for fact in self.corpus.subset("contradictions")
                    )
                continue

            record = await self._run_trial(
                trial_index,
                label,
                subset_name,
                repetitions,
                distractors,
            )
            self.records.append(record)
            path.write_text(
                json.dumps(asdict(record), indent=2),
                encoding="utf-8",
            )

        (self.output_dir / "all_trials.json").write_text(
            json.dumps([asdict(record) for record in self.records], indent=2),
            encoding="utf-8",
        )
        return self.records

    async def _run_trial(
        self,
        trial_index: int,
        label: str,
        subset_name: str,
        repetitions: int,
        n_distractors: int,
    ) -> TrialRecord:
        started = time.perf_counter()
        injection_results = []
        target_facts = self.corpus.subset(subset_name)
        use_contradiction = subset_name == "contradictions"

        for _ in range(n_distractors):
            result = await self.probe.inject_distractor(
                self._distractor_counter
            )
            self._distractor_counter += 1
            injection_results.append(asdict(result))

        for repetition in range(repetitions):
            results = await asyncio.gather(
                *[
                    self.probe.inject_fact(
                        fact,
                        use_contradiction=use_contradiction,
                        trial=trial_index,
                        repetition=repetition,
                    )
                    for fact in target_facts
                ]
            )
            for result in results:
                injection_results.append(asdict(result))
                fact = self.corpus.by_id(result.fact_id)
                fact.injected_count += 1
                fact.last_injected_trial = trial_index

        if use_contradiction:
            self._contradicted_ids.update(fact.id for fact in target_facts)

        if label == "cold_query":
            await self.probe.reset_working_memory()

        query_types = ("direct", "paraphrase", "decoy")
        if not self._warmup_complete and self.config.warmup_replays > 0:
            self.probe.warm_layers_from_history(self.config.warmup_replays)
            self._warmup_complete = True

        if self.config.mode == "generation":
            probe_results = await asyncio.gather(
                *[
                    self.probe.answer_query(fact, query_type)
                    for fact in self.corpus.facts
                    for query_type in query_types
                ]
            )
        else:
            probe_results = await asyncio.gather(
                *[
                    self.probe.retrieve(fact, query_type)
                    for fact in self.corpus.facts
                    for query_type in query_types
                ]
            )
        expanded_facts = [
            fact for fact in self.corpus.facts for _ in query_types
        ]
        judgments = await self.judge.judge_batch(
            expanded_facts,
            probe_results,
            trial_index,
            self._contradicted_ids,
        )

        return TrialRecord(
            trial_index=trial_index,
            label=label,
            subset_name=subset_name,
            repetitions=repetitions,
            distractors_injected=n_distractors,
            injection_results=injection_results,
            judgment_results=[
                {
                    **judgment.as_dict(),
                    "retrieved_chunks": getattr(
                        probe_result,
                        "retrieved_chunks",
                        [],
                    ),
                    "answer": getattr(probe_result, "answer", None),
                    "neural_hint_present": getattr(
                        probe_result,
                        "neural_hint_present",
                        False,
                    ),
                    "query": probe_result.query,
                    "probe_error": probe_result.error,
                }
                for judgment, probe_result in zip(judgments, probe_results)
            ],
            elapsed_sec=time.perf_counter() - started,
            timestamp=time.time(),
            mode=self.config.mode,
        )
