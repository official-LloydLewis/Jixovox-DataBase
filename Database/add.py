# Database/add_user.py
"""
Secure CLI user registration script with:
- Argon2 password hashing + per-user salt + global pepper (with SHA-256 fallback)
- Plain JSON array persistence per role folder
- Rotating logs and stats tracking
- Optional prompt_toolkit enhancements with graceful degradation
- Full type hints and structured exceptions
"""

import sys
import os
import re
import json
import hashlib
import logging
import traceback
import secrets
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Dict, List, Set
from logging.handlers import RotatingFileHandler
from contextlib import nullcontext
from getpass import getpass

try:  # Optional dependency: argon2
    from argon2 import PasswordHasher  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs
    PasswordHasher = None  # type: ignore

try:  # Optional dependency: prompt_toolkit
    from prompt_toolkit import prompt as pt_prompt  # type: ignore
    from prompt_toolkit.completion import WordCompleter  # type: ignore
    from prompt_toolkit.styles import Style as PTStyle  # type: ignore
    from prompt_toolkit.patch_stdout import patch_stdout  # type: ignore
    PROMPT_TOOLKIT_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs
    pt_prompt = None  # type: ignore
    WordCompleter = None  # type: ignore
    PTStyle = None  # type: ignore
    patch_stdout = lambda: nullcontext()
    PROMPT_TOOLKIT_AVAILABLE = False

# -----------------------------
# Constants / Configuration
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
VALID_ROLES = ["Owner", "Developer", "Admin", "Member"]
LOG_FILE = BASE_DIR / "Logs" / "system_log.txt"
STATS_FILE = BASE_DIR / "Logs" / "stats.json"
# Use environment for pepper and encryption key for better security
PEPPER = os.environ.get("APP_PEPPER", "static-pepper")

EMAIL_DOMAINS = ["@gmail.com", "@yahoo.com", "@outlook.com", "@protonmail.com"]
EMAIL_COMPLETER = WordCompleter(EMAIL_DOMAINS, match_middle=True) if WordCompleter else None
STYLE = PTStyle.from_dict({
    "completion-menu": "bg:#222222",
    "completion-menu.completion.current": "bg:#444444 fg:#ffffff",
    "completion-menu.completion": "bg:#222222 fg:#888888",
}) if PTStyle else None

# -----------------------------
# Logging setup
# -----------------------------
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
handler = RotatingFileHandler(LOG_FILE, maxBytes=200000, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[handler]
)

# -----------------------------
# Security utilities
# -----------------------------
if PasswordHasher is not None:
    ph = PasswordHasher()
else:
    ph = None
login_attempts: Dict[str, int] = {}

def hash_password(password: str) -> Dict[str, str]:
    """Return Argon2 hash and unique salt for given password."""
    salt = secrets.token_hex(16)
    salted_pw = password + salt + PEPPER
    if ph is not None:
        hashed = ph.hash(salted_pw)
        algo = "argon2"
    else:
        # Fallback when argon2-cffi is unavailable: use SHA-256 over salted input.
        hashed = hashlib.sha256(salted_pw.encode()).hexdigest()
        algo = "sha256"
    return {"hash": hashed, "salt": salt, "algo": algo}

def verify_password(stored: Dict[str, str], password: str) -> bool:
    """Verify password against stored hash+salt."""
    salted_pw = password + stored.get("salt", "") + PEPPER
    try:
        if ph is not None and stored.get("algo") in (None, "argon2"):
            ph.verify(stored["hash"], salted_pw)
            return True
        expected = hashlib.sha256(salted_pw.encode()).hexdigest()
        return secrets.compare_digest(stored.get("hash", ""), expected)
    except Exception:
        return False

# -----------------------------
# Custom exceptions
# -----------------------------
class UserError(Exception): pass
class ValidationError(UserError): pass
class EmailExistsError(ValidationError): pass
class DatabaseError(UserError): pass

def log_exception(e: Exception) -> None:
    """Log exception with traceback."""
    logging.error(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# -----------------------------
# Brute force protection
# -----------------------------
def check_brute_force(email: str) -> None:
    """Limit login attempts per email to mitigate brute force."""
    attempts = login_attempts.get(email, 0)
    if attempts >= 5:
        raise ValidationError("Too many attempts, try again later.")
    login_attempts[email] = attempts + 1

# -----------------------------
# Validation helpers
# -----------------------------
class Validator:
    @staticmethod
    def name(name: str) -> None:
        if not re.fullmatch(r"[A-Za-z\s]+", name):
            raise ValidationError("Invalid name format.")

    @staticmethod
    def email(email: str) -> None:
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
            raise ValidationError("Invalid email format.")

    @staticmethod
    def password(password: str) -> None:
        # Password must include upper, lower, digit, and special char
        if (
            len(password) < 8
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"\d", password)
            or not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)
        ):
            raise ValidationError("Weak password.")

# -----------------------------
# User database
# -----------------------------
class Users:
    """Manage users stored in a JSON array per role folder."""

    def __init__(self, role_folder: Path, safe_mode: bool = False) -> None:
        self.role_folder = role_folder
        self.db_file = role_folder / "users.json"
        self.cache: List[Dict[str, Any]] = []
        self.email_index: Set[str] = set()
        self.safe_mode = safe_mode
        role_folder.mkdir(parents=True, exist_ok=True)
        if not self.db_file.exists():
            self._initialize_file()
        self._load_cache()

    def _initialize_file(self) -> None:
        """Create an empty JSON array file for users."""
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4)
            f.write("\n")

    def _load_cache(self) -> None:
        """Load all users into memory cache and email index."""
        self.cache = []
        self.email_index = set()
        if not self.db_file.exists():
            return
        try:
            with open(self.db_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise DatabaseError("Users file must contain a JSON array.")
            for user in data:
                if isinstance(user, dict):
                    self.cache.append(user)
                    if "email" in user:
                        self.email_index.add(str(user["email"]))
        except Exception as e:
            raise DatabaseError(f"Load failed: {e}")

    def _save_full(self) -> None:
        """Rewrite the entire database atomically."""
        tmp = self.db_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=4)
            f.write("\n")
        tmp.replace(self.db_file)

    def email_exists(self, email: str) -> bool:
        return email in self.email_index

    def add_user(self, user: Dict[str, Any]) -> None:
        """Add user and persist to storage."""
        # Reload to ensure we have the latest data before appending.
        self._load_cache()
        if self.email_exists(user["email"]):
            raise EmailExistsError("Email already exists.")
        self.cache.append(user)
        self.email_index.add(user["email"])
        self._save_full()

# -----------------------------
# Stats helpers
# -----------------------------
def load_stats() -> Dict[str, Any]:
    """Load global stats JSON, return defaults if missing/corrupt."""
    if not STATS_FILE.exists():
        return {"User_Count": 0}
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"User_Count": 0}

def update_stats(stats: Dict[str, Any]) -> None:
    """Update global stats file with pretty formatting."""
    STATS_FILE.parent.mkdir(exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)

# -----------------------------
# CLI input
# -----------------------------
def ui_input(text: str, password: bool = False) -> str:
    """Prompt user with optional email completion and password masking."""
    prompt_text = f"[SYSTEM] {text}"
    if PROMPT_TOOLKIT_AVAILABLE and pt_prompt is not None:
        with patch_stdout():
            val = pt_prompt(
                prompt_text,
                is_password=password,
                completer=EMAIL_COMPLETER if "Email" in text else None,
                style=STYLE
            ).strip()
    else:
        try:
            if password and sys.stdin.isatty():
                val = getpass(prompt_text)
            else:
                val = input(prompt_text)
        except EOFError:
            raise ValidationError("Input stream closed.")
        val = val.strip()
    if not val:
        raise ValidationError("Empty input.")
    # Basic sanitization to prevent injection in logs
    return re.sub(r"[<>\"']", "", val)

# -----------------------------
# Main flow
# -----------------------------
def main() -> None:
    stats = load_stats()
    new_id = stats.get("User_Count", 0) + 1
    try:
        # Gather and validate user inputs
        name = ui_input("Name: ")
        Validator.name(name)

        email = ui_input("Email: ")
        Validator.email(email)

        password = ui_input("Password: ", password=True)
        Validator.password(password)
        hashed_pw = hash_password(password)

        role = ui_input(f"Role ({', '.join(VALID_ROLES)}): ").capitalize()
        if role not in VALID_ROLES:
            raise ValidationError("Invalid role.")

        # Prepare user record
        user = {
            "id": str(new_id),
            "name": name,
            "email": email,
            "password": hashed_pw,
            "role": role,
            "created": datetime.now(UTC).isoformat()
        }

        # Persist user
        users = Users(BASE_DIR / role)
        users.add_user(user)
        stats["User_Count"] = new_id
        update_stats(stats)

        print("User added successfully.")
    except Exception as e:
        log_exception(e)
        print(f"Error: {e}")

if __name__ == "__main__":
    main()