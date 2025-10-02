# Database/search_users.py
"""
Live search users by name or email across role folders with:
- robust async loading with timeouts and optional escalation of critical errors
- caching
- configurable fuzzy search (uses rapidfuzz when available)
- separated constants/config
- improved prompt_toolkit completer and UX messages
- full type hints and unit tests
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contextlib import nullcontext
from getpass import getpass

# prompt_toolkit for interactive prompt (optional dependency)
try:  # pragma: no cover - exercised in environments without prompt_toolkit
    from prompt_toolkit import prompt as pt_prompt  # type: ignore
    from prompt_toolkit.completion import Completer, Completion  # type: ignore
    from prompt_toolkit.patch_stdout import patch_stdout  # type: ignore
    from prompt_toolkit.shortcuts import clear as pt_clear  # type: ignore
    from prompt_toolkit.styles import Style as PTStyle  # type: ignore
    from prompt_toolkit.key_binding import KeyBindings as PTKeyBindings  # type: ignore
    PROMPT_TOOLKIT_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - fallback path
    pt_prompt = None  # type: ignore
    PROMPT_TOOLKIT_AVAILABLE = False

    class Completer:  # type: ignore
        """Fallback stub to satisfy type hints when prompt_toolkit missing."""

        def __init__(self, *args, **kwargs):
            pass

    class Completion:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    def patch_stdout():
        return nullcontext()

    def pt_clear():
        # Simple fallback: print a couple blank lines instead of full clear
        print("\n" * 2)

    class PTKeyBindings:  # type: ignore
        def add(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    PTStyle = None  # type: ignore

# Local utilities (colors and display_title are expected to exist)
# They should provide ANSI color constants used below; if not present,
# fall back to minimal no-op strings so module still imports.
try:
    from Utils.colors import *
except Exception:
    # Fallbacks if Utils.colors not available to avoid ImportError during tests
    BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = BRIGHT = STYLE_RESET = ""
    LRED = ""

try:
    from Utils.display_title import display_title
except Exception:
    def display_title(*args, **kwargs):
        return None

# Optional fuzzy library
try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz  # type: ignore
except Exception:
    rapidfuzz_fuzz = None  # type: ignore

# ----------------------
# Constants / Config
# ----------------------
KeyBindings = PTKeyBindings  # Alias for unified usage below

DEFAULT_USER_FILE = "users.json"
DEFAULT_ROLES = ("Owner", "Developer", "Admin", "Member")
DEFAULT_REQUIRED_FIELDS = frozenset({"id", "name", "email", "role"})
DEFAULT_USER_LOAD_TIMEOUT = 3  # seconds per file
DEFAULT_FUZZY_THRESHOLD = 75

ROLE_COLORS: Dict[str, Tuple[str, str]] = {
    "Owner": (RED, WHITE),
    "Developer": (YELLOW, WHITE),
    "Admin": (LRED, WHITE),
    "Member": (BLUE, WHITE),
}

# Attempt to import DATABASE_DIR from project handler; fallback to current dir
try:
    from Handler.path_handler import DATABASE_DIR  # type: ignore
    DATABASE_DIR = Path(DATABASE_DIR)
except Exception:
    DATABASE_DIR = Path(__file__).resolve().parent

LOG_DIR = DATABASE_DIR / "Logs"
LOG_FILE = LOG_DIR / "search.log"

# ----------------------
# Logging
# ----------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("search_users")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s | %(message)s'))
    logger.addHandler(fh)

# prompt_toolkit style for completions (small UX improvement)
style = PTStyle.from_dict({
    'completion-menu': 'bg:#222222',
    'completion-menu.completion.current': 'bg:#444444 fg:#ffffff',
    'completion-menu.completion': 'bg:#222222 fg:#888888',
}) if PTStyle else None

# ----------------------
# Exceptions
# ----------------------
class UserSearchError(Exception):
    """Base exception for search-related errors."""

class CriticalDataError(UserSearchError):
    """Raised when a critical data integrity problem is encountered (escalate)."""

# ----------------------
# Models
# ----------------------
@dataclass(frozen=True)
class User:
    id: str
    name: str
    email: str
    role: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["User"]:
        """Return User if dict contains required fields, otherwise None."""
        if not isinstance(data, dict):
            return None
        missing = DEFAULT_REQUIRED_FIELDS - data.keys()
        if missing:
            logger.debug(f"Skipping user with missing fields: {missing}")
            return None
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            email=str(data["email"]),
            role=str(data["role"])
        )

# ----------------------
# Utilities
# ----------------------
def colored_role(role: str) -> str:
    """Return colorized role string for display (best-effort)."""
    role_clean = str(role).capitalize()
    fg_color, bracket_color = ROLE_COLORS.get(role_clean, (WHITE, WHITE))
    return f"{BRIGHT}{bracket_color}[{STYLE_RESET}{fg_color}{role_clean}{STYLE_RESET}{BRIGHT}{bracket_color}]{STYLE_RESET}"

def clear_screen() -> None:
    """Clear the console if possible, otherwise print spacing."""
    if PROMPT_TOOLKIT_AVAILABLE:
        try:
            pt_clear()
            return
        except Exception:
            pass
    # Attempt OS-level clear; fallback to blank lines
    command = "cls" if os.name == "nt" else "clear"
    if os.system(command) != 0:
        print("\n" * 2)

def prompt_text(
    message: str,
    *,
    is_password: bool = False,
    completer=None,
    style=None,
    key_bindings=None,
):
    """Unified prompt helper that degrades gracefully without prompt_toolkit."""
    if PROMPT_TOOLKIT_AVAILABLE and pt_prompt is not None:
        kwargs: Dict[str, Any] = {"is_password": is_password}
        if completer is not None:
            kwargs["completer"] = completer
        if style is not None:
            kwargs["style"] = style
        if key_bindings is not None:
            kwargs["key_bindings"] = key_bindings
        return pt_prompt(message, **kwargs)

    try:
        if is_password:
            try:
                return getpass(message)
            except Exception:
                pass
        return input(message)
    except EOFError as exc:
        raise UserSearchError("Input stream closed.") from exc

def user_to_display(user: User) -> str:
    return f"ID: {user.id} | {colored_role(user.role)} {user.name} | Email: {user.email}"

def show_error(message: str, pause: float = 2.0) -> None:
    """User-friendly error output (prints and clears screen after short pause)."""
    print("\n" + "-" * 60)
    print(f"{LRED}Error:{STYLE_RESET} {message}")
    print("-" * 60 + "\n")
    time.sleep(pause)
    clear_screen()

def ensure_roles_exist(database_dir: Path, roles: Tuple[str, ...]) -> List[Path]:
    """Check role directories exist; return list of existing role directory paths."""
    existing = []
    missing = []
    for role in roles:
        p = database_dir / role
        if p.is_dir():
            existing.append(p)
        else:
            missing.append(role)
    if missing:
        logger.warning(f"Missing role directories: {missing}")
    return existing

# ----------------------
# Loader (async)
# ----------------------
class UserLoader:
    """
    Load and cache users from role directories asynchronously with timeout and error handling.

    Parameters
    ----------
    database_dir: Path
        Root folder that contains role-named subfolders.
    roles: Tuple[str, ...]
        Roles to look for.
    users_file: str
        Name of users file within each role folder.
    timeout: int
        Timeout in seconds for reading each file.
    escalate_on_missing: bool
        If True, treat missing files/folders as critical and raise CriticalDataError.
    """

    def __init__(
        self,
        database_dir: Path,
        roles: Tuple[str, ...] = DEFAULT_ROLES,
        users_file: str = DEFAULT_USER_FILE,
        timeout: int = DEFAULT_USER_LOAD_TIMEOUT,
        escalate_on_missing: bool = False,
    ) -> None:
        self.database_dir = database_dir
        self.roles = roles
        self.users_file = users_file
        self.timeout = timeout
        self.escalate_on_missing = escalate_on_missing
        self._cached_users: List[User] = []
        self._load_semaphore = asyncio.Semaphore(8)  # limit concurrency for disk IO

    async def _read_path_text(self, path: Path) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, path.read_text, "utf-8")

    async def _load_file(self, path: Path) -> List[User]:
        """Attempt to read and parse a users.json file, returning validated Users."""
        async with self._load_semaphore:
            try:
                content = await asyncio.wait_for(self._read_path_text(path), timeout=self.timeout)
                data = json.loads(content)
                if not isinstance(data, list):
                    logger.warning(f"Unexpected format in {path}: expected list, got {type(data)}")
                    return []
                users = []
                for item in data:
                    user = User.from_dict(item)
                    if user:
                        users.append(user)
                    else:
                        logger.debug(f"Ignored invalid user entry in {path}")
                logger.info(f"Loaded {len(users)} valid users from {path}")
                return users
            except asyncio.TimeoutError:
                logger.warning(f"Timeout loading file: {path}")
                # Not critical; return empty and inform user
                show_error(f"Timeout while loading {path.parent.name}/{self.users_file}")
            except json.JSONDecodeError:
                logger.warning(f"Corrupt JSON in file: {path}")
                show_error(f"Corrupt JSON in {path.parent.name}/{self.users_file}")
            except Exception as exc:
                logger.exception(f"Unexpected error loading {path}: {exc}")
                # escalate if requested
                if self.escalate_on_missing:
                    raise CriticalDataError(f"Failed to load {path}: {exc}") from exc
                show_error(f"Failed to load {path.parent.name}/{self.users_file}: {exc}")
            return []

    async def load_all_users(self, refresh: bool = False) -> List[User]:
        """
        Load users from all roles asynchronously and cache result.

        If refresh is True, clears cache and reloads from disk.
        """
        if self._cached_users and not refresh:
            logger.debug("Returning cached users")
            return list(self._cached_users)

        role_dirs = ensure_roles_exist(self.database_dir, self.roles)
        if not role_dirs:
            msg = f"No role directories found in {self.database_dir}."
            logger.error(msg)
            if self.escalate_on_missing:
                raise CriticalDataError(msg)
            show_error(msg)
            return []

        tasks = []
        for role_dir in role_dirs:
            file_path = role_dir / self.users_file
            if file_path.is_file():
                tasks.append(self._load_file(file_path))
            else:
                logger.info(f"Missing users file at {file_path}; skipping.")
                if self.escalate_on_missing:
                    # escalate for missing files if requested
                    raise CriticalDataError(f"Missing required file: {file_path}")
                # else: continue without raising

        results = await asyncio.gather(*tasks, return_exceptions=False)
        users: List[User] = []
        for res in results:
            users.extend(res)

        self._cached_users = users
        logger.info(f"Loaded total {len(users)} users from {len(results)} files")
        return list(users)

    def clear_cache(self) -> None:
        """Clear internal cache to force reload on next call."""
        self._cached_users.clear()

# ----------------------
# Searcher
# ----------------------
class UserSearcher:
    """
    Search through User objects by field with optional fuzzy support.
    """

    def __init__(self, users: List[User], use_fuzzy: bool = False, threshold: int = DEFAULT_FUZZY_THRESHOLD) -> None:
        self.users = users
        self.use_fuzzy = use_fuzzy and (rapidfuzz_fuzz is not None)
        if use_fuzzy and rapidfuzz_fuzz is None:
            # fallback notice — prefer logger for non-interactive consumers
            print("Warning: rapidfuzz not installed; fuzzy search disabled.")
            logger.info("Fuzzy requested but rapidfuzz not available; disabled.")
        self.threshold = int(threshold)

    def _simple_search(self, query: str, field_getter) -> List[User]:
        q = query.lower()
        return [u for u in self.users if q in field_getter(u)]

    def _fuzzy_search(self, query: str, field_getter) -> List[User]:
        # use partial_ratio for substring-like fuzzy matches
        scored: List[Tuple[int, User]] = []
        q = query.lower()
        for u in self.users:
            value = field_getter(u)
            # rapidfuzz expects str inputs; partial_ratio returns 0-100
            score = rapidfuzz_fuzz.partial_ratio(q, value)
            if score >= self.threshold:
                scored.append((score, u))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [user for _, user in scored]

    def search(self, query: str, field: str) -> List[User]:
        """Search users by 'name' or 'email'. Returns list of User objects."""
        if not query or not query.strip():
            return []

        field = field.lower()
        if field not in {"name", "email"}:
            raise ValueError("field must be 'name' or 'email'")

        # Precompute field getter to avoid repeated getattr/str calls
        if field == "name":
            getter = lambda u: u.name.lower()
        else:
            getter = lambda u: u.email.lower()

        # Choose algorithm
        if self.use_fuzzy:
            return self._fuzzy_search(query, getter)
        else:
            return self._simple_search(query, getter)

# ----------------------
# Completer
# ----------------------
class RoleNameCompleter(Completer):
    """
    Efficient completer that suggests based on name and email.
    Filters using simple startswith on lowercase cached values for snappy UX.
    """

    def __init__(self, users: List[User], mode: str) -> None:
        self.mode = mode.lower()
        assert self.mode in {"name", "email"}
        # prepare tuple list for faster iteration: (field_value_lower, display_text, insert_text)
        self._candidates: List[Tuple[str, str, str]] = []
        for u in users:
            field_val = u.name if self.mode == "name" else u.email
            display = f"[{u.role}] {u.name} <{u.email}>"
            self._candidates.append((field_val.lower(), display, field_val))

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lower()
        if not text:
            return  # avoid flooding suggestions when empty

        # yield candidates whose field startswith the typed text, up to 20 suggestions
        count = 0
        for val_lower, display, insert in self._candidates:
            if val_lower.startswith(text):
                yield Completion(insert, start_position=-len(text), display=display)
                count += 1
                if count >= 20:
                    break

# ----------------------
# Logging helper
# ----------------------
def log_action(mode: str, query: str, result_count: int, enable_logging: bool) -> None:
    if not enable_logging:
        return
    try:
        logger.info(f"Search mode: {mode} | Query: '{query}' | Results: {result_count}")
    except Exception:
        # keep search operation resilient even if logging fails
        print("Warning: logging failed", file=sys.stderr)

# ----------------------
# Display results
# ----------------------
def display_results(results: List[User]) -> None:
    if not results:
        print(WHITE + BRIGHT + "\n" + "-" * 50)
        print(LRED + "No matches found.")
        print(WHITE + BRIGHT + "-" * 50 + "\n")
        time.sleep(1.2)
        return
    print(f"\nFound {len(results)} user(s):\n")
    for u in results:
        print(user_to_display(u))

# ----------------------
# Main application flow
# ----------------------
async def main_async(args: argparse.Namespace) -> None:
    """Main async entrypoint for interactive search."""
    enable_logging = bool(args.enable_logging)
    fuzzy_search_flag = bool(args.fuzzy_search)
    fuzzy_threshold = int(args.fuzzy_threshold) if args.fuzzy_threshold is not None else DEFAULT_FUZZY_THRESHOLD

    # Display nice title (if available)
    try:
        display_title("Live User Search")
    except Exception:
        pass

    user_loader = UserLoader(
        DATABASE_DIR,
        roles=tuple(args.roles) if args.roles else DEFAULT_ROLES,
        users_file=args.users_file or DEFAULT_USER_FILE,
        timeout=int(args.load_timeout),
        escalate_on_missing=bool(args.escalate_on_missing),
    )

    try:
        users = await user_loader.load_all_users(refresh=bool(args.refresh_cache))
    except CriticalDataError as cde:
        show_error(str(cde))
        return

    if not users:
        show_error("No users available. Check data folders and users.json files.")
        return

    # Ask mode once at start
    mode_prompt = "Search by 'name' or 'email': "
    mode = prompt_text(mode_prompt, style=style).strip().lower()
    if mode not in {"name", "email"}:
        show_error("Invalid search mode. Use 'name' or 'email'.")
        return

    print(f"\nLive search by {mode}. Start typing... (Press Ctrl+C to exit)\n")

    kb = KeyBindings()

    @kb.add("c-c")
    def _(event):
        event.app.exit()

    # Prepare searcher/completer before loop; can refresh users dynamically if needed
    searcher = UserSearcher(users, use_fuzzy=fuzzy_search_flag, threshold=fuzzy_threshold)
    completer = RoleNameCompleter(users, mode)

    while True:
        try:
            with patch_stdout():
                query = prompt_text(
                    "Search: ",
                    completer=completer,
                    style=style,
                    key_bindings=kb,
                )
        except KeyboardInterrupt:
            print("\nExiting search.")
            break
        except Exception as exc:
            logger.exception(f"Prompt failed: {exc}")
            show_error(f"Prompt error: {exc}")
            break

        results = []
        try:
            results = searcher.search(query, mode)
        except Exception as exc:
            logger.exception(f"Search error: {exc}")
            show_error(f"Search error: {exc}")
            continue

        clear_screen()
        display_results(results)
        log_action(mode, query, len(results), enable_logging)

# ----------------------
# CLI & tests
# ----------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live search users by name or email across role folders.")
    parser.add_argument("--test", action="store_true", help="Run unit tests and exit.")
    parser.add_argument("--enable-logging", action="store_true", help="Enable logging of search queries.")
    parser.add_argument("--fuzzy-search", action="store_true", help="Enable fuzzy search (requires rapidfuzz).")
    parser.add_argument("--fuzzy-threshold", dest="fuzzy_threshold", type=int, default=DEFAULT_FUZZY_THRESHOLD,
                        help=f"Fuzzy match threshold (0-100). Default {DEFAULT_FUZZY_THRESHOLD}.")
    parser.add_argument("--users-file", default=DEFAULT_USER_FILE, help="Name of users file in each role folder.")
    parser.add_argument("--roles", nargs="+", help="Custom role folder names to scan (overrides defaults).")
    parser.add_argument("--load-timeout", default=DEFAULT_USER_LOAD_TIMEOUT, type=int, help="Timeout (seconds) per file load.")
    parser.add_argument("--escalate-on-missing", action="store_true", help="Raise CriticalDataError on missing files/dirs.")
    parser.add_argument("--refresh-cache", action="store_true", help="Force reload users from disk.")
    return parser.parse_args(argv)

def run_tests() -> None:
    import unittest

    class SearchUsersTest(unittest.TestCase):
        def setUp(self):
            self.sample_users = [
                User(id="001", name="LloydLewis", email="lloyd@example.com", role="Owner"),
                User(id="002", name="Jixel", email="jixel@dev.com", role="Developer"),
            ]

        def test_simple_search(self):
            searcher = UserSearcher(self.sample_users)
            results = searcher.search("lloyd", "name")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].name, "LloydLewis")

        def test_fuzzy_search(self):
            if rapidfuzz_fuzz is None:
                self.skipTest("rapidfuzz not installed")
            searcher = UserSearcher(self.sample_users, use_fuzzy=True)
            results = searcher.search("Loyd", "name")
            self.assertTrue(any(u.name == "LloydLewis" for u in results))

        def test_no_results(self):
            searcher = UserSearcher(self.sample_users)
            results = searcher.search("xyz", "name")
            self.assertEqual(len(results), 0)

        def test_empty_query(self):
            searcher = UserSearcher(self.sample_users)
            results = searcher.search("", "name")
            self.assertEqual(len(results), 0)

    class LoaderTest(unittest.IsolatedAsyncioTestCase):
        async def test_load_users_handles_missing_files(self):
            import tempfile
            from pathlib import Path as P
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = P(tmpdir)
                loader = UserLoader(tmp, roles=tuple(["NoRole1", "NoRole2"]), users_file="users.json")
                users = await loader.load_all_users()
                self.assertIsInstance(users, list)
                self.assertEqual(len(users), 0)

    unittest.main(argv=['first-arg-is-ignored'], exit=False)

# ----------------------
# Entrypoint
# ----------------------
if __name__ == "__main__":
    args = parse_args()
    if args.test:
        run_tests()
        sys.exit(0)

    # Run main async loop with basic top-level error handling
    try:
        # apply nest_asyncio only if available so tests and environments like notebooks can run
        try:
            import nest_asyncio  # type: ignore
            nest_asyncio.apply()
        except Exception:
            pass

        asyncio.get_event_loop().run_until_complete(main_async(args))
    except CriticalDataError as cde:
        show_error(f"Critical error: {cde}")
        sys.exit(2)
    except Exception as exc:
        logger.exception(f"Unhandled exception in main: {exc}")
        show_error(f"Unhandled error: {exc}")
        sys.exit(1)
