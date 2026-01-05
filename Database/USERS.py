# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
import json
import re
from pathlib import Path
from threading import Lock
from typing import List, Dict, Optional


class Users:
    """
    Manages role-based JSON user storage with validation, caching, and duplicate checks.

    Features:
    - Role-based storage (Owner, Developer, Admin, Member, Bot)
    - Duplicate detection across all roles
    - Input validation (email format, required fields)
    - Atomic read/write with caching
    - Flexible BASE_DIR
    - Thread-safe operations with file locks
    """

    VALID_ROLES = ['Owner', 'Developer', 'Admin', 'Member', 'Bot']
    REQUIRED_FIELDS = {'id', 'name', 'email', 'role'}

    # In-memory cache for all users to reduce repeated file reads
    _cache: Dict[str, List[Dict]] = {}
    _lock = Lock()

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the Users manager.

        :param base_dir: Base directory for role folders. Defaults to script directory.
        """
        self.BASE_DIR = base_dir or Path(__file__).resolve().parent
        self._ensure_role_folders()

    def _ensure_role_folders(self):
        """
        Ensure all role folders exist, create them if missing.
        """
        for role in self.VALID_ROLES:
            role_path = self.BASE_DIR / role
            role_path.mkdir(parents=True, exist_ok=True)
            users_file = role_path / 'users.json'
            if not users_file.exists():
                self._write_data(role, [])

    def _read_data(self, role: str) -> List[Dict]:
        """
        Read user data from JSON file with caching.

        :param role: Role folder name.
        :return: List of user dicts.
        """
        if role in self._cache:
            return self._cache[role]

        file_path = self.BASE_DIR / role / 'users.json'
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._cache[role] = data
                    return data
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache[role] = []

        return []

    def _write_data(self, role: str, data: List[Dict]):
        """
        Write user data to JSON file atomically and update cache.

        :param role: Role folder name.
        :param data: List of user dicts.
        """
        file_path = self.BASE_DIR / role / 'users.json'
        tmp_file = file_path.with_suffix('.json.tmp')
        try:
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                f.flush()
            tmp_file.replace(file_path)
            self._cache[role] = data
        except Exception as e:
            raise IOError(f"Failed to write data for role {role}: {e}")

    def _validate_user(self, user: Dict):
        """
        Validate required fields and email format.

        :param user: User dictionary.
        :raises ValueError: If validation fails.
        """
        missing = self.REQUIRED_FIELDS - user.keys()
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        # Email regex validation
        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, user['email']):
            raise ValueError(f"Invalid email format: {user['email']}")

        if user['role'] not in self.VALID_ROLES:
            raise ValueError(f"Invalid role: {user['role']}")

    def add_user(self, user_info: Dict):
        """
        Add a new user after validation and duplicate check.

        :param user_info: User dictionary containing id, name, email, role.
        :raises ValueError: If user is duplicate or invalid.
        """
        self._validate_user(user_info)

        with self._lock:
            if self.is_duplicate(user_info['name'], user_info['email']):
                raise ValueError("User with same name or email exists in another role.")

            role = user_info['role']
            users = self._read_data(role)
            users.append(user_info)
            self._write_data(role, users)

    @classmethod
    def is_duplicate(cls, name: str, email: str) -> bool:
        """
        Check if a user with the same name or email exists across all roles.

        :param name: Name of user.
        :param email: Email of user.
        :return: True if duplicate exists, False otherwise.
        """
        for role in cls.VALID_ROLES:
            role_folder = Path(__file__).resolve().parent / role
            users_file = role_folder / 'users.json'
            if users_file.exists():
                try:
                    with open(users_file, 'r', encoding='utf-8') as f:
                        users = json.load(f)
                        for user in users:
                            if user.get('name') == name or user.get('email') == email:
                                return True
                except json.JSONDecodeError:
                    continue
        return False

    def list_all_users(self) -> List[Dict]:
        """
        Return a flattened list of all users across all roles.

        :return: List of all user dicts.
        """
        all_users = []
        for role in self.VALID_ROLES:
            all_users.extend(self._read_data(role))
        return all_users

    def find_user(self, query: str) -> List[Dict]:
        """
        Search users by name, email, or ID (case-insensitive).

        :param query: Search string.
        :return: List of matching users.
        """
        query_lower = query.lower()
        results = []
        for user in self.list_all_users():
            if query_lower in str(user.get('id', '')).lower() \
               or query_lower in user.get('name', '').lower() \
               or query_lower in user.get('email', '').lower():
                results.append(user)
        return results
