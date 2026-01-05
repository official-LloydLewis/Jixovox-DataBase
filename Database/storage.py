# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
"""Storage adapter abstractions for database role/user files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Protocol

from Handler.config_loader import Config


class StorageAdapter(Protocol):
    """Interface for loading and persisting role user data."""

    config: Config

    def load_role_users(self, role: str, users_file: str) -> List[Dict[str, Any]]:
        """Load users for the given role."""

    def write_role_users(self, role: str, users: List[Dict[str, Any]], users_file: str) -> None:
        """Persist users for the given role."""

    def update_stats(self, total_users: int) -> None:
        """Write aggregate statistics."""


@dataclass
class JsonStorageAdapter:
    """JSON file-backed implementation of :class:`StorageAdapter`."""

    config: Config

    def _role_dir(self, role: str) -> Path:
        return self.config.database_dir / role

    def load_role_users(self, role: str, users_file: str) -> List[Dict[str, Any]]:
        path = self._role_dir(role) / users_file
        if not path.exists():
            return []

        content = path.read_text(encoding="utf-8")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

        if not isinstance(data, list):
            raise ValueError(f"Unexpected content in {path}: expected a list of users")
        return data

    def write_role_users(self, role: str, users: List[Dict[str, Any]], users_file: str) -> None:
        role_path = self._role_dir(role)
        role_path.mkdir(parents=True, exist_ok=True)
        path = role_path / users_file
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(users, indent=4, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def update_stats(self, total_users: int) -> None:
        self.config.stats_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"User_Count": total_users}
        self.config.stats_file.write_text(json.dumps(payload, indent=4), encoding="utf-8")
