import json
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict

@dataclass
class Episode:
    """Single episode in episodic memory."""
    id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    importance: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "text": self.text,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "importance": self.importance,
        }
    
    @classmethod
    def from_chromadb(cls, id: str, document: str, metadata: Dict[str, Any]) -> "Episode":
        return cls(
            id=id,
            timestamp=metadata.get("timestamp", time.time()),
            text=document,
            metadata=json.loads(metadata.get("metadata", "{}")) if isinstance(metadata.get("metadata"), str) else metadata.get("metadata", {}),
            session_id=metadata.get("session_id"),
            project_id=metadata.get("project_id"),
            importance=metadata.get("importance", 0.5),
        )
