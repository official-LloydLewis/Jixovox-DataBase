# Database/add_user.py
"""
Secure CLI user registration script with:
- Argon2 password hashing + per-user salt + global pepper
- Fernet encryption for sensitive fields
- gzip JSON Lines database per role
- Rotating logs and stats tracking
- prompt_toolkit for interactive UX
- Full type hints and structured exceptions
"""

import sys
import os
import re
import json
import gzip
import logging
import traceback
import secrets
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Dict, List, Set
from argon2 import PasswordHasher
from logging.handlers import RotatingFileHandler
from cryptography.fernet import Fernet, InvalidToken
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.patch_stdout import patch_stdout

# -----------------------------
# Constants / Configuration
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
VALID_ROLES = ["Owner", "Developer", "Admin", "Member"]
LOG_FILE = BASE_DIR / "Logs" / "system_log.txt"
STATS_FILE = BASE_DIR / "Logs" / "stats.json"
# Use environment for pepper and encryption key for better security
PEPPER = os.environ.get("APP_PEPPER", "static-pepper")
ENC_KEY = os.environ.get("APP_ENC_KEY", Fernet.generate_key().decode())

EMAIL_DOMAINS = ["@gmail.com", "@yahoo.com", "@outlook.com", "@protonmail.com"]
EMAIL_COMPLETER = WordCompleter(EMAIL_DOMAINS, match_middle=True)
STYLE = PTStyle.from_dict({
    "completion-menu": "bg:#222222",
    "completion-menu.completion.current": "bg:#444444 fg:#ffffff",
    "completion-menu.completion": "bg:#222222 fg:#888888",
})

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
ph = PasswordHasher()
fernet = Fernet(ENC_KEY.encode())
login_attempts: Dict[str, int] = {}

def encrypt_data(data: str) -> str:
    """Encrypt text using Fernet symmetric encryption."""
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(token: str) -> str:
    """Decrypt token; return placeholder if unreadable."""
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return "[UNREADABLE]"

def hash_password(password: str) -> Dict[str, str]:
    """Return Argon2 hash and unique salt for given password."""
    salt = secrets.token_hex(16)
    salted_pw = password + salt + PEPPER
    hashed = ph.hash(salted_pw)
    return {"hash": hashed, "salt": salt}

def verify_password(stored: Dict[str, str], password: str) -> bool:
    """Verify password against stored hash+salt."""
    try:
        ph.verify(stored["hash"], password + stored["salt"] + PEPPER)
        return True
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
    """
    Manage users stored in gzip-compressed JSON Lines format per role folder.
    Supports safe_mode for atomic full rewrites or faster append-only mode.
    """

    def __init__(self, role_folder: Path, safe_mode: bool = False) -> None:
        self.role_folder = role_folder
        self.db_file = role_folder / "users.jsonl.gz"
        self.cache: List[Dict[str, Any]] = []
        self.email_index: Set[str] = set()
        self.safe_mode = safe_mode
        role_folder.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    def _load_cache(self) -> None:
        """Load all users into memory cache and email index."""
        if not self.db_file.exists():
            return
        try:
            with gzip.open(self.db_file, "rt", encoding="utf-8") as f:
                for line in f:
                    user = json.loads(line)
                    self.cache.append(user)
                    if "email" in user:
                        self.email_index.add(user["email"])
        except Exception as e:
            raise DatabaseError(f"Load failed: {e}")

    def _save_full(self) -> None:
        """Rewrite the entire database atomically (safe mode)."""
        tmp = self.db_file.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            for u in self.cache:
                f.write(json.dumps(u) + "\n")
        tmp.replace(self.db_file)

    def _append(self, user: Dict[str, Any]) -> None:
        """Append new user to database for performance."""
        with gzip.open(self.db_file, "at", encoding="utf-8") as f:
            f.write(json.dumps(user) + "\n")

    def email_exists(self, email: str) -> bool:
        return email in self.email_index

    def add_user(self, user: Dict[str, Any]) -> None:
        """Add user and persist to storage."""
        if self.email_exists(user["email"]):
            raise EmailExistsError("Email already exists.")
        self.cache.append(user)
        self.email_index.add(user["email"])
        if self.safe_mode:
            self._save_full()
        else:
            self._append(user)

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
    with patch_stdout():
        val = prompt(
            f"[SYSTEM] {text}",
            is_password=password,
            completer=EMAIL_COMPLETER if "Email" in text else None,
            style=STYLE
        ).strip()
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
            "name": encrypt_data(name),
            "email": encrypt_data(email),
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