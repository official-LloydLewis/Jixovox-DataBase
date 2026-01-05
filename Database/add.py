# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
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
import hashlib
import time
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Set
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
try:
    fernet = Fernet(ENC_KEY.encode())
except Exception:
    fernet = Fernet(Fernet.generate_key())
login_attempts: Dict[str, int] = {}

def _norm_email(e: str) -> str:
    return e.strip().lower()

def _hash_email(e: str) -> str:
    return hashlib.sha256(_norm_email(e).encode()).hexdigest()

def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(token: str) -> str:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return "[UNREADABLE]"

def hash_password(password: str) -> Dict[str, str]:
    salt = secrets.token_hex(16)
    salted_pw = password + salt + PEPPER
    hashed = ph.hash(salted_pw)
    return {"hash": hashed, "salt": salt}

def verify_password(stored: Dict[str, str], password: str) -> bool:
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
    logging.error(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# -----------------------------
# Brute force protection
# -----------------------------
def check_brute_force(email: str) -> None:
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
        if (
            len(password) < 8
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"\d", password)
            or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password)
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
        self.email_index: Set[str, int] = set()
        self.safe_mode = safe_mode
        role_folder.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.db_file.exists():
            return
        try:
            with gzip.open(self.db_file, "rt", encoding="utf-8") as f:
                for line in f:
                    user = json.loads(line)
                    self.cache.append(user)
                    if "email" in user:
                        plain = decrypt_data(user["email"]) if user["email"] else ""
                        if plain and plain != "[UNREADABLE]":
                            self.email_index.add(_hash_email(plain))
        except Exception as e:
            raise DatabaseError(f"Load failed: {e}")

    def _save_full(self) -> None:
        tmp = self.db_file.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            for u in self.cache:
                f.write(json.dumps(u) + "\n")
        tmp.replace(self.db_file)

    def _append(self, user: Dict[str, Any]) -> None:
        with gzip.open(self.db_file, "at", encoding="utf-8") as f:
            f.write(json.dumps(user) + "\n")

    def email_exists(self, email: str) -> bool:
        candidate = email
        if "@" not in candidate:
            candidate = decrypt_data(candidate)
        return _hash_email(candidate) in self.email_index

    def add_user(self, user: Dict[str, Any]) -> None:
        candidate = user.get("email", "")
        if self.email_exists(candidate):
            raise EmailExistsError("Email already exists.")
        self.cache.append(user)
        plain = decrypt_data(candidate) if "@" not in candidate else candidate
        if plain and plain != "[UNREADABLE]":
            self.email_index.add(_hash_email(plain))
        if self.safe_mode:
            self._save_full()
        else:
            self._append(user)

# -----------------------------
# Plaintext mirror for compatibility with other tools
# -----------------------------
def _mirror_plain_users_json(role_folder: Path, user_plain: Dict[str, Any]) -> None:
    dst = role_folder / "users.json"
    try:
        existing = []
        if dst.exists():
            data = json.loads(dst.read_text("utf-8"))
            if isinstance(data, list):
                existing = data
        by_key = {}
        for u in existing:
            key = (str(u.get("id")), _norm_email(str(u.get("email", ""))))
            by_key[key] = u
        key = (str(user_plain.get("id")), _norm_email(user_plain.get("email", "")))
        by_key[key] = user_plain
        merged = list(by_key.values())
        tmp = dst.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=4, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dst)
    except Exception as e:
        log_exception(e)

# -----------------------------
# Stats helpers
# -----------------------------
def load_stats() -> Dict[str, Any]:
    if not STATS_FILE.exists():
        return {"User_Count": 0}
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"User_Count": 0}

def update_stats(stats: Dict[str, Any]) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)

# -----------------------------
# CLI input
# -----------------------------
def _print_error_box(message: str) -> None:
    red = "\033[1;31m"
    reset = "\033[0m"
    print(f"{red}===========================\nError: {message}\n==========================={reset}")


def ui_input(text: str, password: bool = False) -> str:
    with patch_stdout():
        val = prompt(
            f"[SYSTEM] {text}",
            is_password=password,
            completer=EMAIL_COMPLETER if "Email" in text else None,
            style=STYLE
        ).strip()
    if not val:
        raise ValidationError("Empty input.")
    return re.sub(r"[<>\"']", "", val)


def prompt_with_validation(
    text: str,
    validator: Callable[[str], None] | None = None,
    password: bool = False,
) -> str:
    while True:
        try:
            value = ui_input(text, password=password)
            if validator:
                validator(value)
            return value
        except Exception as exc:
            _print_error_box(str(exc))
            time.sleep(1)
            try:
                from Utils.display_title import display_title
                display_title()
            except Exception:
                pass

# -----------------------------
# Main flow
# -----------------------------
def main() -> None:
    try:
        from Utils.display_title import display_title
        display_title()
    except Exception:
        pass

    stats = load_stats()
    new_id = stats.get("User_Count", 0) + 1
    try:
        name = prompt_with_validation("Name: ", Validator.name)
        email = prompt_with_validation("Email: ", Validator.email)
        password = prompt_with_validation("Password: ", Validator.password, password=True)
        hashed_pw = hash_password(password)
        role = prompt_with_validation(f"Role ({', '.join(VALID_ROLES)}): ")
        role = role.capitalize()
        if role not in VALID_ROLES:
            raise ValidationError("Invalid role.")
        users = Users(BASE_DIR / role)
        if users.email_exists(email):
            raise EmailExistsError("Email already exists.")
        user = {
            "id": str(new_id),
            "name": encrypt_data(name),
            "email": encrypt_data(email),
            "password": hashed_pw,
            "role": role,
            "created": datetime.now(UTC).isoformat()
        }
        users.add_user(user)
        _mirror_plain_users_json(BASE_DIR / role, {
            "id": str(new_id),
            "name": name,
            "email": email,
            "password": hashed_pw,
            "role": role,
            "created": datetime.now(UTC).isoformat()
        })
        stats["User_Count"] = new_id
        update_stats(stats)
        print("User added successfully.")
    except Exception as e:
        log_exception(e)
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
