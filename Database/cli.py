"""
Unified CLI entrypoint that wraps the existing database utilities.

Subcommands
-----------
- add, search, update, remove: delegate to the existing interactive scripts.
- export, import, backup: use the export_import helpers.

Examples
--------
Run interactive add flow::

    python Database/cli.py add

Create a backup with retention::

    python Database/cli.py backup --retention 5
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from Database import export_import  # noqa: E402


SCRIPT_MAP = {
    "add": SCRIPTS_DIR / "add.py",
    "search": SCRIPTS_DIR / "search.py",
    "update": SCRIPTS_DIR / "update.py",
    "remove": SCRIPTS_DIR / "remove.py",
}


def _run_script(path: Path, extra_args: Optional[List[str]] = None) -> int:
    cmd = [sys.executable, str(path)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified entrypoint for database utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("add", "search", "update", "remove"):
        sub.add_parser(name, help=f"Run the {name} utility")

    export_parser = sub.add_parser("export", help="Export users to snapshot")
    export_parser.add_argument("-o", "--output", type=Path, help="Destination file")
    export_parser.add_argument("--users-file", default=export_import.USER_FILE, help="Filename per role")

    import_parser = sub.add_parser("import", help="Import users from snapshot")
    import_parser.add_argument("-f", "--file", type=Path, required=True, help="Snapshot to import")
    import_parser.add_argument("--mode", choices=["merge", "replace"], default="merge", help="Merge or replace data")
    import_parser.add_argument("--users-file", default=export_import.USER_FILE, help="Filename per role")

    backup_parser = sub.add_parser("backup", help="Create backup and prune old exports")
    backup_parser.add_argument("--retention", type=int, help="Number of exports to retain")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command in SCRIPT_MAP:
        return _run_script(SCRIPT_MAP[args.command])

    if args.command == "export":
        destination = export_import.export_database(args.output, users_file=args.users_file)
        print(f"Snapshot written to: {destination}")
        return 0

    if args.command == "import":
        summary = export_import.import_database(args.file, mode=args.mode, users_file=args.users_file)
        print("Import complete")
        for role, count in summary["roles_updated"].items():
            print(f"  {role}: {count} record(s) processed")
        print(f"Total users after import: {summary['total_users']}")
        return 0

    if args.command == "backup":
        destination = export_import.run_backup(retention=args.retention)
        print(f"Backup created at: {destination}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
