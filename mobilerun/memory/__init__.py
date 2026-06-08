"""Persistent Memory Store for Mobilerun.

Provides cross-session key-value memory backed by a JSON file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("mobilerun")

DEFAULT_DIR = Path.home() / ".local" / "share" / "mobilerun"
DEFAULT_PATH = DEFAULT_DIR / "memory.json"


class MemoryEntry:
    """A single memory entry with metadata."""

    def __init__(self, value: Any, source: str = "agent", updated_at: str | None = None):
        self.value = value
        self.source = source
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            value=data["value"],
            source=data.get("source", "agent"),
            updated_at=data.get("updated_at"),
        )


class MemoryStore:
    """Persistent memory storage backed by a JSON file.

    Supports get/set/delete/list/search operations on a simple key-value store.
    Entries are timestamped and attributed (source tracking).
    """

    def __init__(self, path: str | Path | None = None, max_entries: int = 100):
        self._path = Path(path) if path else DEFAULT_PATH
        self._max_entries = max_entries
        self._entries: Dict[str, dict] = {}
        self._load()

    # -- public API ----------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key. Returns None if not found."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        return entry["value"]

    def set(self, key: str, value: Any, source: str = "agent") -> None:
        """Save or update a value."""
        self._entries[key] = MemoryEntry(value=value, source=source).to_dict()
        self._enforce_limit()
        self._save()

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        if key in self._entries:
            del self._entries[key]
            self._save()
            return True
        return False

    def list_keys(self) -> list[str]:
        """Return all stored keys."""
        return list(self._entries.keys())

    def list_all(self) -> Dict[str, Any]:
        """Return all entries as {key: value}."""
        return {k: v["value"] for k, v in self._entries.items()}

    def search(self, query: str) -> list[tuple[str, Any]]:
        """Simple substring search across values. Returns [(key, value), ...]."""
        query_lower = query.lower()
        results = []
        for key, entry in self._entries.items():
            val_str = str(entry["value"]).lower()
            if query_lower in val_str or query_lower in key.lower():
                results.append((key, entry["value"]))
        return results

    def clear(self) -> None:
        """Remove all entries."""
        self._entries.clear()
        self._save()

    def entry_count(self) -> int:
        return len(self._entries)

    # -- internal ------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = data.get("entries", {})
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load memory store: {e}")
            self._entries = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump({"entries": self._entries}, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to save memory store: {e}")

    def _enforce_limit(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._entries) > self._max_entries:
            oldest_key = min(
                self._entries,
                key=lambda k: self._entries[k].get("updated_at", ""),
            )
            del self._entries[oldest_key]
            logger.debug(f"Memory store: evicted oldest entry '{oldest_key}'")
