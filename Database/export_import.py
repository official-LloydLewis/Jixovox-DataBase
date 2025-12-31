"""
Utilities for exporting and importing role-based user data.

Features
--------
- Export all role folders into a single JSON snapshot with metadata.
- Import a snapshot in merge or replace mode with duplicate protection.
- Lightweight validation of user objects and automatic stats refresh.
- CLI with explicit subcommands: ``export`` and ``import``.

Usage examples
--------------
Export all users to ``Database/data/exports/users-export-<timestamp>.json``::

    python Database/export_import.py export

Import from a snapshot while replacing existing records::

    python Database/export_import.py import --file path/to/snapshot.json --mode replace

The utilities operate on the plain ``users.json`` files that back the
interactive CLI tools.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ROLES: Tuple[str, ...] = ("Owner", "Developer", "Admin", "Member", "Bot")
USER_FILE = "users.json"
EXPORTS_DIR = BASE_DIR / "data" / "exports"
STATS_FILE = BASE_DIR / "Logs" / "stats.json"
REQUIRED_FIELDS = frozenset({"id", "name", "email", "role"})


def _role_dir(role: str) -> Path:
    return BASE_DIR / role


def _load_role_users(role: str, users_file: str) -> List[Dict[str, Any]]:
    path = _role_dir(role) / users_file
    if not path.exists():
        return []

    content = path.read_text("utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Unexpected content in {path}: expected a list of users")
    return data


def _write_role_users(role: str, users: List[Dict[str, Any]], users_file: str) -> None:
    role_path = _role_dir(role)
    role_path.mkdir(parents=True, exist_ok=True)
    path = role_path / users_file
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(users, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _normalize_user(user: Dict[str, Any], role: str) -> Dict[str, Any]:
    if not isinstance(user, dict):
        raise ValueError("User entries must be dictionaries")

    missing = REQUIRED_FIELDS - user.keys()
    if missing:
        raise ValueError(f"Missing required fields for {role}: {', '.join(sorted(missing))}")

    normalized = dict(user)
    normalized["role"] = role
    normalized["id"] = str(normalized.get("id", "")).strip()
    normalized["name"] = str(normalized.get("name", "")).strip()
    normalized["email"] = str(normalized.get("email", "")).strip()
    return normalized


def _dedupe_users(users: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, int] = {}
    deduped: List[Dict[str, Any]] = []

    for user in users:
        email_key = str(user.get("email", "")).lower()
        identifier = email_key or str(user.get("id", ""))
        if identifier in seen:
            # Prefer the most recent entry by overwriting in place
            deduped[seen[identifier]] = user
        else:
            seen[identifier] = len(deduped)
            deduped.append(user)
    return deduped


def _reindex_ids(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reindexed: List[Dict[str, Any]] = []
    for idx, user in enumerate(users, start=1):
        updated = dict(user)
        updated["id"] = str(idx)
        reindexed.append(updated)
    return reindexed


def _update_stats(total_users: int) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"User_Count": total_users}
    STATS_FILE.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def export_database(output: Path | None = None, users_file: str = USER_FILE) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = output or EXPORTS_DIR / f"users-export-{timestamp}.json"

    snapshot: Dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "roles": DEFAULT_ROLES,
            "users_file": users_file,
        },
        "users": {},
    }

    total_users = 0
    for role in DEFAULT_ROLES:
        users = _load_role_users(role, users_file)
        snapshot["users"][role] = users
        total_users += len(users)

    snapshot["metadata"]["user_count"] = total_users
    target.write_text(json.dumps(snapshot, indent=4, ensure_ascii=False), encoding="utf-8")
    return target


def import_database(snapshot_path: Path, mode: str = "merge", users_file: str = USER_FILE) -> Dict[str, Any]:
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    raw = json.loads(snapshot_path.read_text("utf-8"))
    users_section = raw.get("users")
    if not isinstance(users_section, dict):
        raise ValueError("Snapshot is missing a valid 'users' section")

    imported_counts: Dict[str, int] = {}
    total_after_import = 0

    for role, entries in users_section.items():
        if role not in DEFAULT_ROLES:
            continue

        incoming_raw = entries if isinstance(entries, list) else []
        incoming = [_normalize_user(user, role) for user in incoming_raw]

        if mode == "merge":
            existing = _load_role_users(role, users_file)
            merged = _dedupe_users([*existing, *incoming])
        else:
            merged = _dedupe_users(incoming)

        merged = _reindex_ids(merged)
        _write_role_users(role, merged, users_file)
        imported_counts[role] = len(incoming)
        total_after_import += len(merged)

    _update_stats(total_after_import)
    return {"roles_updated": imported_counts, "total_users": total_after_import}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export or import role-based user data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Create a JSON snapshot of all roles")
    export_parser.add_argument("-o", "--output", type=Path, help="Destination file for the snapshot")
    export_parser.add_argument("--users-file", default=USER_FILE, help="Filename that stores users per role")

    import_parser = subparsers.add_parser("import", help="Load users from a snapshot file")
    import_parser.add_argument("-f", "--file", type=Path, required=True, help="Snapshot file to import")
    import_parser.add_argument("--mode", choices=["merge", "replace"], default="merge", help="Merge with or replace existing data")
    import_parser.add_argument("--users-file", default=USER_FILE, help="Filename that stores users per role")

    return parser


def main(argv: List[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "export":
        destination = export_database(args.output, users_file=args.users_file)
        print(f"Snapshot written to: {destination}")
    elif args.command == "import":
        summary = import_database(args.file, mode=args.mode, users_file=args.users_file)
        print("Import complete")
        for role, count in summary["roles_updated"].items():
            print(f"  {role}: {count} record(s) processed")
        print(f"Total users after import: {summary['total_users']}")


if __name__ == "__main__":
    main()
