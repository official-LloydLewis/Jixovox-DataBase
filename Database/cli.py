# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
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

Forward extra options to an underlying script::

    python Database/cli.py add -- --role Owner
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from Database import export_import  # noqa: E402


@dataclass(frozen=True)
class ScriptCommand:
    name: str
    path: Path
    help: str


SCRIPT_COMMANDS: Dict[str, ScriptCommand] = {
    "add": ScriptCommand("add", SCRIPTS_DIR / "add.py", "Run the add utility"),
    "search": ScriptCommand("search", SCRIPTS_DIR / "search.py", "Run the search utility"),
    "update": ScriptCommand("update", SCRIPTS_DIR / "update.py", "Run the update utility"),
    "remove": ScriptCommand("remove", SCRIPTS_DIR / "remove.py", "Run the remove utility"),
}


def _run_script(path: Path, extra_args: Optional[List[str]] = None) -> int:
    cmd = [sys.executable, str(path)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd)
    return result.returncode


def _add_script_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for script in SCRIPT_COMMANDS.values():
        parser = subparsers.add_parser(
            script.name,
            help=script.help,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument(
            "script_args",
            nargs=argparse.REMAINDER,
            help="Arguments forwarded to the underlying script",
        )
        parser.set_defaults(handler=lambda args, script=script: _run_script(script.path, args.script_args))


def _add_export_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "export",
        help="Export users to snapshot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-o", "--output", type=Path, help="Destination file")
    parser.add_argument("--users-file", default=export_import.USER_FILE, help="Filename per role")
    parser.set_defaults(
        handler=lambda args: _print_and_return(
            f"Snapshot written to: {export_import.export_database(args.output, users_file=args.users_file)}"
        )
    )


def _add_import_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "import",
        help="Import users from snapshot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-f", "--file", type=Path, required=True, help="Snapshot to import")
    parser.add_argument("--mode", choices=["merge", "replace"], default="merge", help="Merge or replace data")
    parser.add_argument("--users-file", default=export_import.USER_FILE, help="Filename per role")
    parser.set_defaults(handler=_handle_import)


def _add_backup_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "backup",
        help="Create backup and prune old exports",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--retention", type=int, help="Number of exports to retain")
    parser.set_defaults(
        handler=lambda args: _print_and_return(
            f"Backup created at: {export_import.run_backup(retention=args.retention)}"
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified entrypoint for database utilities",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="Jixovox Database CLI 1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    _add_script_subcommand(sub)
    _add_export_subcommand(sub)
    _add_import_subcommand(sub)
    _add_backup_subcommand(sub)

    return parser


def _handle_import(args: argparse.Namespace) -> int:
    summary = export_import.import_database(args.file, mode=args.mode, users_file=args.users_file)
    print("Import complete")
    for role, count in summary.roles_updated.items():
        print(f"  {role}: {count} record(s) processed")
    print(f"Total users after import: {summary.total_users}")
    return 0


def _print_and_return(message: str, code: int = 0) -> int:
    print(message)
    return code


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handler: Optional[Callable[[argparse.Namespace], int]] = getattr(args, "handler", None)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
