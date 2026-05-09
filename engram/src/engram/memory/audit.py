"""Memory audit/lint operation for Engram.

Read-only diagnostic pass that surfaces problems without modifying memory.
Six checks identify orphans, contradictions, stale data, weak rules, dangling
relations, and near-duplicate rules. Findings are returned as structured
data; the user inspects and decides what to remediate via a separate
audit_remediate() entry point on ProjectMemory.

Design philosophy:
- Read-only by default — mutation is opt-in and explicit
- Project-scoped — never bleeds across project boundaries
- Cheap-first — uses lexical heuristics, no LLM calls
- Pluggable checks — each is a standalone function for easy extension

Author: Jeffrey Dean
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# --- Constants ---------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "error"
_SEVERITY_RANK = {SEVERITY_ERROR: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}

# Defaults — tunable per-call via audit_memory(...)
DEFAULT_STALE_DAYS = 180
DEFAULT_LOW_CONFIDENCE = 0.65
DEFAULT_CONTRADICTION_OVERLAP = 0.7
DEFAULT_DUPLICATE_OVERLAP = 0.85

# Polarity markers used by cheap contradiction check
_NEGATION_TERMS = frozenset({
    "no", "not", "never", "none", "neither", "nor", "without",
    "cannot", "cant", "wont", "isnt", "arent", "wasnt", "werent",
    "dont", "doesnt", "didnt", "havent", "hasnt", "hadnt",
})
_OPPOSITES = [
    ("always", "never"),
    ("must", "cannot"),
    ("required", "forbidden"),
    ("enable", "disable"),
    ("allow", "block"),
    ("increase", "decrease"),
    ("add", "remove"),
    ("on", "off"),
]


# --- Data structures ---------------------------------------------------------

@dataclass
class AuditFinding:
    """A single problem discovered during an audit pass."""
    check_name: str
    severity: str  # info / warn / error
    record_id: str
    record_type: str  # episode / fact / rule / relation
    details: str
    suggested_action: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "severity": self.severity,
            "record_id": self.record_id,
            "record_type": self.record_type,
            "details": self.details,
            "suggested_action": self.suggested_action,
            "extra": dict(self.extra),
        }


@dataclass
class AuditReport:
    """Aggregate result of an audit pass."""
    project_id: str
    findings: List[AuditFinding] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)
    checks_skipped: Dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    audit_timestamp: float = field(default_factory=time.time)

    @property
    def count(self) -> int:
        return len(self.findings)

    def by_severity(self, severity: str) -> List[AuditFinding]:
        return [f for f in self.findings if f.severity == severity]

    def by_check(self, check_name: str) -> List[AuditFinding]:
        return [f for f in self.findings if f.check_name == check_name]

    def sorted_findings(self) -> List[AuditFinding]:
        """Findings sorted by severity (error > warn > info), stable."""
        return sorted(
            self.findings,
            key=lambda f: _SEVERITY_RANK.get(f.severity, 99),
        )

    def summary(self) -> Dict[str, int]:
        counts = {"error": 0, "warn": 0, "info": 0}
        for f in self.findings:
            if f.severity in counts:
                counts[f.severity] += 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "findings": [f.to_dict() for f in self.findings],
            "checks_run": list(self.checks_run),
            "checks_skipped": dict(self.checks_skipped),
            "summary": self.summary(),
            "elapsed_seconds": self.elapsed_seconds,
            "audit_timestamp": self.audit_timestamp,
        }

    def to_markdown(self) -> str:
        """Human-readable Markdown report grouped by severity."""
        lines = [f"# Memory Audit — project `{self.project_id}`"]
        lines.append("")
        s = self.summary()
        lines.append(
            f"**Summary:** {s['error']} error / {s['warn']} warn / "
            f"{s['info']} info  ({self.count} total findings)"
        )
        lines.append(f"_Checks run: {', '.join(self.checks_run) or '(none)'}_")
        if self.checks_skipped:
            skipped = ", ".join(
                f"{k} ({v})" for k, v in self.checks_skipped.items()
            )
            lines.append(f"_Checks skipped: {skipped}_")
        lines.append(f"_Elapsed: {self.elapsed_seconds:.2f}s_")
        lines.append("")

        for severity in (SEVERITY_ERROR, SEVERITY_WARN, SEVERITY_INFO):
            group = self.by_severity(severity)
            if not group:
                continue
            lines.append(f"## {severity.upper()} ({len(group)})")
            for f in group:
                lines.append(
                    f"- **[{f.check_name}]** {f.record_type} `{f.record_id}` — "
                    f"{f.details}"
                )
                if f.suggested_action:
                    lines.append(f"  - _Suggested:_ {f.suggested_action}")
            lines.append("")

        if not self.findings:
            lines.append("_No findings — memory is clean._")
        return "\n".join(lines)


# --- Helper utilities --------------------------------------------------------

def _tokenize(text: str) -> Set[str]:
    """Lowercase word-token set, matches retrieval.py tokenizer style."""
    if not text:
        return set()
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _has_polarity_conflict(text_a: str, text_b: str) -> bool:
    """Detect cheap polarity conflict between two highly-similar texts.

    Returns True when one text contains a negation term the other lacks,
    or when the two texts contain opposing word pairs (always/never, etc.).
    """
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)

    neg_a = bool(tokens_a & _NEGATION_TERMS)
    neg_b = bool(tokens_b & _NEGATION_TERMS)
    if neg_a != neg_b:
        return True

    for pos, neg in _OPPOSITES:
        a_pos = pos in tokens_a
        a_neg = neg in tokens_a
        b_pos = pos in tokens_b
        b_neg = neg in tokens_b
        if (a_pos and b_neg) or (a_neg and b_pos):
            return True
    return False


# --- Individual checks -------------------------------------------------------

def check_orphan_synthesis(
    semantic, episodic, project_id: str,
) -> List[AuditFinding]:
    """Synthesis rules whose support_episode_ids no longer exist."""
    findings: List[AuditFinding] = []
    if semantic is None:
        return findings

    # Pull all rules for the project — bypass FTS, direct table scan
    try:
        rows = semantic._reader().execute(
            "SELECT id, rule_text, support_episode_ids "
            "FROM synthesized_rules WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    except Exception as exc:
        logger.debug("check_orphan_synthesis: %s", exc)
        return findings

    if not rows:
        return findings

    # Build set of valid episode IDs (one query) — episodic exposes get_recent
    valid_ids: Set[str] = set()
    if episodic is not None:
        try:
            episodes = episodic.get_recent_episodes(
                n=10000, days_back=3650, project_id=project_id
            )
            valid_ids = {ep.id for ep in episodes if getattr(ep, "id", None)}
        except Exception as exc:
            logger.debug("check_orphan_synthesis: episodic fetch: %s", exc)

    import json as _json
    for rule_id, rule_text, support_json in rows:
        try:
            support_ids = _json.loads(support_json) if support_json else []
        except Exception:
            support_ids = []
        if not support_ids:
            continue

        missing = [eid for eid in support_ids if eid not in valid_ids]
        if not missing:
            continue
        all_missing = len(missing) == len(support_ids)
        severity = SEVERITY_ERROR if all_missing else SEVERITY_WARN
        findings.append(AuditFinding(
            check_name="orphan_synthesis",
            severity=severity,
            record_id=rule_id,
            record_type="rule",
            details=(
                f"Rule cites {len(missing)}/{len(support_ids)} missing "
                f"episodes: {missing[:3]}{'...' if len(missing) > 3 else ''}"
            ),
            suggested_action=(
                "tombstone rule (all support missing)" if all_missing
                else "decay_confidence (partial support missing)"
            ),
            extra={"missing_count": len(missing),
                   "total_support": len(support_ids),
                   "rule_text_preview": (rule_text or "")[:80]},
        ))
    return findings


def check_contradicting_facts(
    semantic, project_id: str,
    overlap_threshold: float = DEFAULT_CONTRADICTION_OVERLAP,
) -> List[AuditFinding]:
    """Pairs of facts with high lexical similarity but opposing polarity."""
    findings: List[AuditFinding] = []
    if semantic is None:
        return findings

    try:
        rows = semantic._reader().execute(
            "SELECT id, content, timestamp FROM facts "
            "ORDER BY timestamp DESC LIMIT 500",
        ).fetchall()
    except Exception as exc:
        logger.debug("check_contradicting_facts: %s", exc)
        return findings

    # Pre-tokenize once
    items = [(r[0], r[1] or "", _tokenize(r[1] or ""), float(r[2] or 0))
             for r in rows]

    seen_pairs: Set[Tuple[str, str]] = set()
    for i in range(len(items)):
        id_a, text_a, toks_a, ts_a = items[i]
        if not toks_a:
            continue
        for j in range(i + 1, len(items)):
            id_b, text_b, toks_b, ts_b = items[j]
            if not toks_b:
                continue
            sim = _jaccard(toks_a, toks_b)
            if sim < overlap_threshold:
                continue
            if not _has_polarity_conflict(text_a, text_b):
                continue
            pair_key = tuple(sorted((id_a, id_b)))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Newer fact wins by convention — older is the suspect
            older_id = id_a if ts_a < ts_b else id_b
            newer_id = id_b if older_id == id_a else id_a
            findings.append(AuditFinding(
                check_name="contradicting_facts",
                severity=SEVERITY_WARN,
                record_id=older_id,
                record_type="fact",
                details=(
                    f"Conflicts with newer fact `{newer_id}` "
                    f"(sim={sim:.2f}, polarity differs)"
                ),
                suggested_action="tombstone older fact (review first)",
                extra={
                    "newer_fact_id": newer_id,
                    "similarity": round(sim, 3),
                    "preview_a": text_a[:80],
                    "preview_b": text_b[:80],
                },
            ))
    return findings


def check_stale_facts(
    semantic, project_id: str,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> List[AuditFinding]:
    """Facts older than threshold with no recent validation."""
    findings: List[AuditFinding] = []
    if semantic is None:
        return findings
    cutoff = time.time() - (stale_days * 86400)

    try:
        rows = semantic._reader().execute(
            "SELECT id, content, timestamp FROM facts "
            "WHERE timestamp < ? "
            "ORDER BY timestamp ASC LIMIT 200",
            (cutoff,),
        ).fetchall()
    except Exception as exc:
        logger.debug("check_stale_facts: %s", exc)
        return findings

    for fact_id, text, ts in rows:
        age_days = int((time.time() - float(ts or 0)) / 86400)
        findings.append(AuditFinding(
            check_name="stale_facts",
            severity=SEVERITY_INFO,
            record_id=fact_id,
            record_type="fact",
            details=f"Fact is {age_days} days old, never re-validated",
            suggested_action="mark_validated if still accurate, else tombstone",
            extra={"age_days": age_days,
                   "preview": (text or "")[:80]},
        ))
    return findings


def check_low_confidence_rules(
    semantic, project_id: str,
    confidence_threshold: float = DEFAULT_LOW_CONFIDENCE,
) -> List[AuditFinding]:
    """Synthesis rules with confidence below threshold."""
    findings: List[AuditFinding] = []
    if semantic is None:
        return findings

    try:
        rows = semantic._reader().execute(
            "SELECT id, rule_text, confidence, support_count "
            "FROM synthesized_rules "
            "WHERE project_id = ? AND confidence < ? "
            "ORDER BY confidence ASC LIMIT 100",
            (project_id, float(confidence_threshold)),
        ).fetchall()
    except Exception as exc:
        logger.debug("check_low_confidence_rules: %s", exc)
        return findings

    for rule_id, rule_text, conf, support in rows:
        findings.append(AuditFinding(
            check_name="low_confidence_rules",
            severity=SEVERITY_INFO,
            record_id=rule_id,
            record_type="rule",
            details=(
                f"Rule confidence {float(conf or 0):.2f} below threshold "
                f"{confidence_threshold:.2f} (support={int(support or 0)})"
            ),
            suggested_action=(
                "tombstone if support hasn't grown after re-synthesis"
            ),
            extra={
                "confidence": round(float(conf or 0), 3),
                "support_count": int(support or 0),
                "preview": (rule_text or "")[:80],
            },
        ))
    return findings


def check_dangling_relations(
    semantic, episodic, project_id: str,
) -> List[AuditFinding]:
    """Relations whose subject_id or object_id no longer exists."""
    findings: List[AuditFinding] = []
    if semantic is None:
        return findings

    try:
        rel_rows = semantic._reader().execute(
            "SELECT id, relation_type, subject_id, object_id "
            "FROM synthesized_relations WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    except Exception as exc:
        logger.debug("check_dangling_relations: %s", exc)
        return findings
    if not rel_rows:
        return findings

    # Collect all valid IDs across rules, facts, episodes
    valid_ids: Set[str] = set()
    try:
        valid_ids.update(
            r[0] for r in semantic._reader().execute(
                "SELECT id FROM synthesized_rules WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        )
        valid_ids.update(
            r[0] for r in semantic._reader().execute(
                "SELECT id FROM facts",
            ).fetchall()
        )
    except Exception as exc:
        logger.debug("check_dangling_relations: id fetch: %s", exc)

    if episodic is not None:
        try:
            eps = episodic.get_recent_episodes(
                n=10000, days_back=3650, project_id=project_id,
            )
            valid_ids.update(ep.id for ep in eps if getattr(ep, "id", None))
        except Exception as exc:
            logger.debug("check_dangling_relations: episodic: %s", exc)

    for rel_id, rtype, subj, obj in rel_rows:
        missing_ends = []
        if subj not in valid_ids:
            missing_ends.append(f"subject={subj}")
        if obj not in valid_ids:
            missing_ends.append(f"object={obj}")
        if not missing_ends:
            continue
        findings.append(AuditFinding(
            check_name="dangling_relations",
            severity=SEVERITY_WARN,
            record_id=str(rel_id),
            record_type="relation",
            details=f"{rtype} relation has missing endpoints: {', '.join(missing_ends)}",
            suggested_action="delete_relation",
            extra={"relation_type": rtype, "subject_id": subj, "object_id": obj},
        ))
    return findings


def check_near_duplicate_rules(
    semantic, project_id: str,
    overlap_threshold: float = DEFAULT_DUPLICATE_OVERLAP,
) -> List[AuditFinding]:
    """Synthesis rules with high lexical overlap (different IDs, near-same text)."""
    findings: List[AuditFinding] = []
    if semantic is None:
        return findings

    try:
        rows = semantic._reader().execute(
            "SELECT id, rule_text, confidence, support_count, timestamp "
            "FROM synthesized_rules WHERE project_id = ? "
            "ORDER BY timestamp DESC LIMIT 500",
            (project_id,),
        ).fetchall()
    except Exception as exc:
        logger.debug("check_near_duplicate_rules: %s", exc)
        return findings

    items = [(r[0], r[1] or "", _tokenize(r[1] or ""),
              float(r[2] or 0), int(r[3] or 0), float(r[4] or 0))
             for r in rows]

    reported: Set[str] = set()
    for i in range(len(items)):
        id_a, text_a, toks_a, conf_a, sup_a, ts_a = items[i]
        if not toks_a or id_a in reported:
            continue
        for j in range(i + 1, len(items)):
            id_b, text_b, toks_b, conf_b, sup_b, ts_b = items[j]
            if not toks_b or id_b in reported:
                continue
            sim = _jaccard(toks_a, toks_b)
            if sim < overlap_threshold:
                continue
            # Suspect = weaker rule (lower confidence × support_count)
            score_a = conf_a * (sup_a + 1)
            score_b = conf_b * (sup_b + 1)
            weaker_id, stronger_id = (
                (id_a, id_b) if score_a < score_b else (id_b, id_a)
            )
            reported.add(weaker_id)
            findings.append(AuditFinding(
                check_name="near_duplicate_rules",
                severity=SEVERITY_INFO,
                record_id=weaker_id,
                record_type="rule",
                details=(
                    f"Near-duplicate of `{stronger_id}` (sim={sim:.2f}); "
                    f"weaker rule by confidence×support"
                ),
                suggested_action="tombstone weaker duplicate",
                extra={
                    "stronger_rule_id": stronger_id,
                    "similarity": round(sim, 3),
                    "preview_weaker": text_a[:80] if weaker_id == id_a else text_b[:80],
                    "preview_stronger": text_b[:80] if weaker_id == id_a else text_a[:80],
                },
            ))
    return findings


# --- Check registry ----------------------------------------------------------

# Each entry: name -> (callable, category)
# Category tells the orchestrator which layers a check needs.
CHECKS: Dict[str, Tuple[Callable, Tuple[str, ...]]] = {
    "orphan_synthesis":     (check_orphan_synthesis,     ("semantic", "episodic")),
    "contradicting_facts":  (check_contradicting_facts,  ("semantic",)),
    "stale_facts":          (check_stale_facts,          ("semantic",)),
    "low_confidence_rules": (check_low_confidence_rules, ("semantic",)),
    "dangling_relations":   (check_dangling_relations,   ("semantic", "episodic")),
    "near_duplicate_rules": (check_near_duplicate_rules, ("semantic",)),
}


# --- Orchestrator ------------------------------------------------------------

def run_audit(
    semantic,
    episodic,
    project_id: str,
    checks: Optional[Iterable[str]] = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    confidence_threshold: float = DEFAULT_LOW_CONFIDENCE,
    contradiction_overlap: float = DEFAULT_CONTRADICTION_OVERLAP,
    duplicate_overlap: float = DEFAULT_DUPLICATE_OVERLAP,
) -> AuditReport:
    """Run audit checks against the memory layers and return a report.

    Args:
        semantic: SemanticMemory instance (or None).
        episodic: EpisodicMemory instance (or None).
        project_id: Project to scope all checks to.
        checks: Iterable of check names to run; None runs all.
        stale_days, confidence_threshold, contradiction_overlap,
        duplicate_overlap: Tunables for individual checks.

    Returns:
        AuditReport with findings sorted by severity.
    """
    selected = list(checks) if checks else list(CHECKS.keys())
    report = AuditReport(project_id=project_id)
    t0 = time.time()

    for name in selected:
        if name not in CHECKS:
            report.checks_skipped[name] = "unknown_check"
            continue
        fn, needs = CHECKS[name]
        if "semantic" in needs and semantic is None:
            report.checks_skipped[name] = "semantic_unavailable"
            continue
        if "episodic" in needs and episodic is None:
            report.checks_skipped[name] = "episodic_unavailable"
            continue

        try:
            if name == "stale_facts":
                findings = fn(semantic, project_id, stale_days=stale_days)
            elif name == "low_confidence_rules":
                findings = fn(semantic, project_id,
                              confidence_threshold=confidence_threshold)
            elif name == "contradicting_facts":
                findings = fn(semantic, project_id,
                              overlap_threshold=contradiction_overlap)
            elif name == "near_duplicate_rules":
                findings = fn(semantic, project_id,
                              overlap_threshold=duplicate_overlap)
            elif "episodic" in needs:
                findings = fn(semantic, episodic, project_id)
            else:
                findings = fn(semantic, project_id)
            report.findings.extend(findings)
            report.checks_run.append(name)
        except Exception as exc:
            logger.warning("audit check %s failed: %s", name, exc)
            report.checks_skipped[name] = f"failed: {exc}"

    report.elapsed_seconds = time.time() - t0
    # Sort findings by severity for predictable output
    report.findings = report.sorted_findings()
    return report
