"""
Lightweight configuration loader with environment and optional .env support.

The loader centralizes common paths for the database utilities so scripts
can share the same base directory, exports location, and stats file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def _read_env_file(env_path: Path) -> Dict[str, str]:
    if not env_path.exists():
        return {}
    data: Dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


@dataclass(frozen=True)
class Config:
    project_root: Path
    database_dir: Path
    exports_dir: Path
    stats_file: Path
    backup_retention: int


def load_config(env_path: Optional[Path] = None, overrides: Optional[Dict[str, str]] = None) -> Config:
    env_file = env_path or DEFAULT_ENV_PATH
    env_data = _read_env_file(env_file)
    override_data = overrides or {}

    def _get(key: str, default: str) -> str:
        return override_data.get(key) or os.environ.get(key) or env_data.get(key) or default

    project_root = Path(_get("PROJECT_ROOT", str(PROJECT_ROOT))).resolve()
    database_dir = Path(_get("DATABASE_DIR", str(project_root / "Database"))).resolve()
    exports_dir = Path(_get("EXPORTS_DIR", str(database_dir / "data" / "exports"))).resolve()
    stats_file = Path(_get("STATS_FILE", str(database_dir / "Logs" / "stats.json"))).resolve()
    backup_retention = int(_get("BACKUP_RETENTION", "5"))

    return Config(
        project_root=project_root,
        database_dir=database_dir,
        exports_dir=exports_dir,
        stats_file=stats_file,
        backup_retention=backup_retention,
    )
