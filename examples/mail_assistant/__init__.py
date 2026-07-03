"""Local, fixture-first mail assistant example."""

from .services import MailAssistantService, SnapshotState
from .store import AssistantStore

__all__ = ["AssistantStore", "MailAssistantService", "SnapshotState"]
