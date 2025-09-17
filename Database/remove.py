# Database/remove.py
"""
Interactive user removal from role folders with:
- Async/thread-safe file operations with locks
- Backup before deletion
- Fuzzy search for name/email matching
- Multi-step confirmation with improved UX
- Structured user data with TypedDict
- Robust JSON load/save with clear exceptions
- prompt_toolkit dialogs with enhanced color-coded messages
- Configurable roles and user file paths
- Internal unit tests for verification
"""

import asyncio
import json
import logging
import threading
import shutil
from pathlib import Path
from typing import List, Dict, Optional, TypedDict, Tuple

from prompt_toolkit import prompt
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.shortcuts import radiolist_dialog

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # fallback exact match

# =====================
# Config / Constants
# =====================
DEFAULT_ROLES: Tuple[str, ...] = ("Owner", "Developer", "Admin", "Member")
DEFAULT_USER_FILE: str = "users.json"
CONFIRM_VALUES: set[str] = {"y", "yes"}
LOG_NAME: str = "delete_user"
LOG_FILE_NAME: str = "delete_user.log"
DATABASE_DIR = Path(__file__).resolve().parent / "Database"
UNITS_DIR = Path(__file__).resolve().parent.parent / "Units"
_file_lock = threading.Lock()

# =====================
# Optional Imports
# =====================
try:
    from ..Utils.colors import *
except Exception:
    RED = GREEN = YELLOW = LRED = BRIGHT = WHITE = STYLE_RESET = ""

try:
    from ..Utils.display_title import display_title
except Exception:
    def display_title(*args, **kwargs): return None

# =====================
# Logging
# =====================
def setup_logger() -> logging.Logger:
    """Setup file logger"""
    log_dir = DATABASE_DIR / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOG_NAME)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename.endswith(LOG_FILE_NAME)
               for h in logger.handlers):
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(log_dir / LOG_FILE_NAME, encoding="utf-8")
        fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s | %(message)s'))
        logger.addHandler(fh)
    return logger

logger = setup_logger()

# =====================
# Prompt Toolkit Style
# =====================
style = PTStyle.from_dict({
    'completion-menu': 'bg:#1f1f1f',
    'completion-menu.completion.current': 'bg:#444444 fg:#ffffff',
    'completion-menu.completion': 'bg:#222222 fg:#cccccc',
    'prompt': 'bold #00ffff',
})

# =====================
# User Type
# =====================
class User(TypedDict, total=False):
    id: str
    name: str
    email: str

# =====================
# Helpers
# =====================
async def async_read_file(path: Path, timeout: int = 5) -> str:
    """Read file async with timeout"""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, path.read_text, "utf-8"), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout reading {path}")
        return ""
    except Exception as e:
        logger.exception(f"Error reading {path}: {e}")
        return ""

def backup_file(path: Path) -> None:
    """Create backup of file"""
    if path.exists():
        backup_path = path.with_suffix(".bak")
        shutil.copy2(path, backup_path)
        logger.info(f"Backup created: {backup_path}")

def load_users(file_path: Path) -> List[User]:
    """Load users from JSON"""
    if not file_path.exists():
        raise FileNotFoundError(f"User file not found: {file_path}")
    try:
        data = json.loads(file_path.read_text("utf-8"))
        if not isinstance(data, list):
            raise ValueError("Expected list in JSON")
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")

def save_users(file_path: Path, users: List[User]) -> None:
    """Save users to JSON thread-safe"""
    try:
        with _file_lock, file_path.open("w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Failed to save {file_path}: {e}")
        raise

def confirm_action(prompt_text: str) -> bool:
    ans = prompt(prompt_text, style=style).strip().lower()
    return ans in CONFIRM_VALUES

def safe_user_info(user: User) -> str:
    return f"id:{user.get('id')} name:{user.get('name','')}"

def fuzzy_match(query: str, user: User) -> bool:
    query = query.lower()
    if user.get("id") == query:
        return True
    for field in ("name", "email"):
        val = user.get(field, "").lower()
        if fuzz and fuzz.partial_ratio(query, val) > 80:
            return True
        if query in val:
            return True
    return False

# =====================
# Core Logic
# =====================
def delete_user_from_role(role_dir: Path, query: str) -> Optional[bool]:
    user_file = role_dir / DEFAULT_USER_FILE
    backup_file(user_file)
    users = load_users(user_file)
    if not users:
        return None

    matches = [u for u in users if fuzzy_match(query, u)]
    if not matches:
        logger.info(f"No match in {role_dir.name}")
        return False

    selected = matches[0]
    if len(matches) > 1:
        choices = [(str(idx), f"{u['name']} | {u['email']} | id:{u['id']}") for idx, u in enumerate(matches)]
        result = radiolist_dialog(title=f"Delete user in {role_dir.name}",
                                  text="Multiple matches found. Choose one:",
                                  values=choices).run()
        if result is None:
            logger.info("Cancelled")
            print(YELLOW + "✗ Cancelled" + STYLE_RESET)
            return None
        selected = matches[int(result)]

    print(RED + f"→ Deleting: {selected['name']} | {selected['email']} (id:{selected['id']})" + STYLE_RESET)
    if not confirm_action(f"{RED}Confirm delete? [y/N]: {STYLE_RESET}"):
        logger.info("Deletion aborted")
        print(YELLOW + "✗ Aborted" + STYLE_RESET)
        return None

    remaining = [u for u in users if u != selected]
    for idx, user in enumerate(remaining, start=1):
        if str(user.get("id", "")).isdigit():
            user["id"] = str(idx)

    save_users(user_file, remaining)
    logger.info(f"Deleted {safe_user_info(selected)} from {role_dir.name}")
    print(GREEN + f"✔ Successfully deleted user from {role_dir.name}" + STYLE_RESET)
    return True

def delete_user(query: str, role: Optional[str] = None) -> None:
    roles = [role] if role else list(DEFAULT_ROLES)
    deleted_roles: List[str] = []

    for r in roles:
        role_path = DATABASE_DIR / r
        if not role_path.is_dir():
            continue
        result = delete_user_from_role(role_path, query)
        if result:
            deleted_roles.append(r)

    if deleted_roles:
        print(GREEN + f"✔ Deleted in: {', '.join(deleted_roles)}" + STYLE_RESET)
    else:
        print(LRED + "✗ No match found" + STYLE_RESET)

# =====================
# Main
# =====================
def main() -> None:
    try:
        display_title("Delete User")
    except Exception:
        pass

    print(WHITE + BRIGHT + "Delete user by ID, name, or email" + STYLE_RESET)
    print("-" * 50)

    try:
        query = prompt("Enter ID, name, or email: ", style=style).strip()
        if not query:
            print(YELLOW + "✗ No input" + STYLE_RESET)
            return

        role_choice = radiolist_dialog(title="Role Selection",
                                       text="Delete from specific role or all?",
                                       values=[("all", "All Roles")] + [(r, r) for r in DEFAULT_ROLES]).run()

        if role_choice is None:
            logger.info("Role selection cancelled")
            print(YELLOW + "✗ Cancelled" + STYLE_RESET)
            return

        if not confirm_action(f"{RED}Confirm search & delete? [y/N]: {STYLE_RESET}"):
            print(YELLOW + "✗ Aborted" + STYLE_RESET)
            return

        delete_user(query, None if role_choice == "all" else role_choice)

    except KeyboardInterrupt:
        print(YELLOW + "\n✗ Cancelled by user" + STYLE_RESET)
    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        print(LRED + f"✗ Error: {e}" + STYLE_RESET)

# =====================
# Unit Test (internal)
# =====================
def _run_unit_tests() -> None:
    test_dir = DATABASE_DIR / "Test"
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / DEFAULT_USER_FILE
    test_users = [
        {"id": "1", "name": "Alice", "email": "alice@test.com"},
        {"id": "2", "name": "Bob", "email": "bob@test.com"},
    ]
    save_users(test_file, test_users)
    assert len(load_users(test_file)) == 2
    assert fuzzy_match("Alice", test_users[0])
    assert fuzzy_match("bob@test.com", test_users[1])
    delete_user_from_role(test_dir, "Alice")
    remaining = load_users(test_file)
    assert len(remaining) == 1 and remaining[0]["name"] == "Bob"
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    main()
