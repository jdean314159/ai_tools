from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class SemanticGraph:
    """NetworkX-based semantic graph with JSON persistence.

    Nodes: facts (fact:xxxxx) and entities (entity:xxxxx)
    Edges: relations (about, superseded_by, prefers, decided, corrected)
    """

    def __init__(self, persist_path: Optional[Path] = None):
        try:
            import networkx as nx
        except ImportError as exc:
            raise ImportError("networkx is a required engram dependency; reinstall engram") from exc

        self.graph: nx.DiGraph = nx.DiGraph()
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path and self.persist_path.exists():
            self.load()

    def add_fact(
        self,
        fact_id: str,
        fact_type: str,
        subject: str,
        value: Any,
        confidence: float = 0.8,
        source_episode_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = time.time()
        self.graph.add_node(
            fact_id,
            node_type="fact",
            fact_type=fact_type,
            subject=subject,
            value=str(value),
            text=self._format_text(fact_type, subject, value),
            confidence=float(confidence),
            created_at=now,
            accessed_at=now,
            access_count=0,
            source_episode_id=source_episode_id,
            superseded=False,
            metadata=metadata or {},
        )
        subject_node = f"entity:{subject}"
        if not self.graph.has_node(subject_node):
            self.graph.add_node(
                subject_node,
                node_type="entity",
                text=subject,
                created_at=now,
                accessed_at=now,
            )
        self.graph.add_edge(
            fact_id,
            subject_node,
            relation_type="about",
            confidence=confidence,
            created_at=now,
        )
        return fact_id

    def add_relation(
        self, source_id: str, target_id: str, relation_type: str, confidence: float = 0.8
    ):
        if not self.graph.has_node(source_id):
            raise ValueError(f"Source node not found: {source_id}")
        if not self.graph.has_node(target_id):
            raise ValueError(f"Target node not found: {target_id}")
        self.graph.add_edge(
            source_id,
            target_id,
            relation_type=relation_type,
            confidence=float(confidence),
            created_at=time.time(),
        )

    def supersede_fact(self, old_fact_id: str, new_fact_id: str):
        if not self.graph.has_node(old_fact_id):
            logger.warning(f"Old fact not found: {old_fact_id}")
            return
        if not self.graph.has_node(new_fact_id):
            logger.warning(f"New fact not found: {new_fact_id}")
            return
        self.graph.nodes[old_fact_id]["superseded"] = True
        self.graph.nodes[old_fact_id]["superseded_at"] = time.time()
        self.add_relation(old_fact_id, new_fact_id, "superseded_by", 1.0)
        logger.info(f"Fact {old_fact_id} superseded by {new_fact_id}")

    def query_facts(
        self,
        subject: Optional[str] = None,
        fact_type: Optional[str] = None,
        include_superseded: bool = False,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        now = time.time()
        facts = []
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") != "fact":
                continue
            if not include_superseded and attrs.get("superseded"):
                continue
            if subject and attrs.get("subject") != subject:
                continue
            if fact_type and attrs.get("fact_type") != fact_type:
                continue
            age_days = (now - attrs.get("created_at", now)) / 86400.0
            recency = max(0.5, 1.0 - (age_days / 90.0))
            facts.append(
                {
                    "id": node_id,
                    "fact_type": attrs.get("fact_type"),
                    "subject": attrs.get("subject"),
                    "value": attrs.get("value"),
                    "text": attrs.get("text"),
                    "confidence": attrs.get("confidence"),
                    "score": attrs.get("confidence", 0.5) * recency,
                    "created_at": attrs.get("created_at"),
                    "superseded": attrs.get("superseded", False),
                    "metadata": attrs.get("metadata", {}),
                }
            )
        facts.sort(key=lambda f: f["score"], reverse=True)
        for fact in facts[:limit]:
            self.graph.nodes[fact["id"]]["accessed_at"] = now
            self.graph.nodes[fact["id"]]["access_count"] = (
                self.graph.nodes[fact["id"]].get("access_count", 0) + 1
            )
        return facts[:limit]

    def forget_low_importance_facts(
        self, min_confidence: float = 0.1, min_age_days: int = 30, max_to_prune: int = 100
    ) -> int:
        now = time.time()
        cutoff = now - (min_age_days * 86400)
        to_remove = []
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") != "fact":
                continue
            if (
                attrs.get("confidence", 0.5) < min_confidence
                and attrs.get("created_at", now) < cutoff
                and attrs.get("accessed_at", attrs.get("created_at", now)) < cutoff
                and attrs.get("access_count", 0) == 0
            ):
                to_remove.append(node_id)
            if len(to_remove) >= max_to_prune:
                break
        for node_id in to_remove:
            self.graph.remove_node(node_id)
        logger.info(f"Pruned {len(to_remove)} low-importance facts")
        return len(to_remove)

    def forget_superseded_facts(self, min_age_days: int = 90) -> int:
        now = time.time()
        cutoff = now - (min_age_days * 86400)
        to_remove = [
            node_id
            for node_id, attrs in self.graph.nodes(data=True)
            if attrs.get("node_type") == "fact"
            and attrs.get("superseded")
            and attrs.get("superseded_at", attrs.get("created_at", now)) < cutoff
        ]
        for node_id in to_remove:
            self.graph.remove_node(node_id)
        logger.info(f"Removed {len(to_remove)} superseded facts")
        return len(to_remove)

    def decay_importance(self, decay_rate: float = 0.95, period_days: int = 7):
        now = time.time()
        period_seconds = period_days * 86400
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") != "fact":
                continue
            accessed_at = attrs.get("accessed_at", attrs.get("created_at", now))
            periods = int((now - accessed_at) / period_seconds)
            if periods > 0:
                new_conf = attrs.get("confidence", 0.5) * (decay_rate**periods)
                self.graph.nodes[node_id]["confidence"] = max(0.0, new_conf)

    def save(self):
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [{"id": nid, **attrs} for nid, attrs in self.graph.nodes(data=True)],
            "edges": [
                {"source": u, "target": v, **attrs} for u, v, attrs in self.graph.edges(data=True)
            ],
            "metadata": {
                "node_count": self.graph.number_of_nodes(),
                "edge_count": self.graph.number_of_edges(),
                "saved_at": time.time(),
            },
        }
        # Write to a temp file then atomically rename to avoid corrupt JSON on
        # crash or KeyboardInterrupt mid-write (os.replace is atomic on POSIX).
        import os

        tmp = self.persist_path.with_suffix(".tmp")
        try:
            with tmp.open("w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.persist_path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def load(self):
        if not self.persist_path or not self.persist_path.exists():
            return
        with self.persist_path.open() as f:
            data = json.load(f)
        self.graph.clear()
        for node_data in data.get("nodes", []):
            node_id = node_data.pop("id")
            self.graph.add_node(node_id, **node_data)
        for edge_data in data.get("edges", []):
            source = edge_data.pop("source")
            target = edge_data.pop("target")
            self.graph.add_edge(source, target, **edge_data)

    def get_stats(self) -> Dict[str, Any]:
        fact_nodes = sum(1 for _, a in self.graph.nodes(data=True) if a.get("node_type") == "fact")
        entity_nodes = sum(
            1 for _, a in self.graph.nodes(data=True) if a.get("node_type") == "entity"
        )
        superseded = sum(
            1
            for _, a in self.graph.nodes(data=True)
            if a.get("node_type") == "fact" and a.get("superseded")
        )
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "fact_nodes": fact_nodes,
            "entity_nodes": entity_nodes,
            "superseded_facts": superseded,
        }

    def _format_text(self, fact_type: str, subject: str, value: Any) -> str:
        if fact_type == "preference":
            return f"Prefers {value} for {subject}"
        elif fact_type == "decision":
            return f"Decided: {value} for {subject}"
        elif fact_type == "correction":
            return f"Corrected: {subject} is {value}"
        return f"{subject}: {value}"
