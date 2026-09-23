# plugins/__init__.py
from .base import EventBus, PluginBase
from .firestore_poller import FirestorePollerPlugin
from .notebooklm_cli import NotebookLMCLIPlugin
from .local_storage import LocalStoragePlugin

__all__ = [
    "EventBus",
    "PluginBase",
    "FirestorePollerPlugin",
    "NotebookLMCLIPlugin",
    "LocalStoragePlugin",
]
