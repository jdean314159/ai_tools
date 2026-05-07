from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SchemaManager:
    """Track schema version for backward compatibility."""

    SCHEMA_FILE = "schema_version.json"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.schema_path = self.project_dir / self.SCHEMA_FILE

    def get_version(self) -> Optional[str]:
        if not self.schema_path.exists():
            return None
        try:
            with self.schema_path.open() as f:
                return json.load(f).get("version")
        except Exception as e:
            logger.warning(f"Failed to read schema version: {e}")
            return None

    def set_version(self, version: str, metadata: Optional[dict] = None):
        from engram import __version__
        data = {
            "version": version,
            "engram_lite_version": __version__,
            "created_at": time.time(),
            "metadata": metadata or {},
        }
        self.project_dir.mkdir(parents=True, exist_ok=True)
        with self.schema_path.open("w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Set schema version to {version}")

    def needs_migration(self, current_version: str) -> bool:
        stored = self.get_version()
        if stored is None:
            return current_version != "1.0"
        return stored != current_version
