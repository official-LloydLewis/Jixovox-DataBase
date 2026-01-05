# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
# Database/update.py
"""
Interactive JSON user editor with:
- Role-based JSON databases (Owner, Developer, Admin, Member)
- Atomic saves to prevent data corruption
- Fuzzy search by name, email, or ID
- prompt_toolkit interactive editor with keybindings:
    - CTRL+S: Save
    - CTRL+X: Cancel
    - CTRL+K: Cut
    - CTRL+U: Paste
    - CTRL+A: Select all
    - CTRL+Z: Undo
- Auto-logging of edits
- Validation of required fields: id, name, email, role
- Clear error reporting and recovery from corrupted JSON
- Cross-platform (Windows / Unix) terminal clearing
- Modular, type-hinted, and production-ready
"""

import sys
import os
import io
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter, FuzzyCompleter
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.application import Application
from prompt_toolkit.clipboard import ClipboardData

# ----- Config & Paths -----
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Utils.colors import *
from Utils.display_title import *

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from Handler.path_handler import DATABASE_DIR  # type: ignore
    DATABASE_DIR = Path(DATABASE_DIR)
except Exception:
    DATABASE_DIR = Path(__file__).resolve().parent

ROLES = ["Owner", "Developer", "Admin", "Member"]
USERS_FILE = "users.json"
REQUIRED_FIELDS = {"id", "name", "email", "role"}
ENABLE_LOGGING = True
LOG_DIR = DATABASE_DIR / "Logs"
LOG_FILE = LOG_DIR / "edit_user.log"

style = PTStyle.from_dict({
    'completion-menu': 'bg:#222222',
    'completion-menu.completion.current': 'bg:#444444 fg:#ffffff',
    'completion-menu.completion': 'bg:#222222 fg:#888888',
    'status': 'reverse',
})

# ----- Utilities -----
def log(msg: str) -> None:
    """
    Append a timestamped message to the edit_user.log file.
    Wraps file writes in try/except to prevent crashes if logging fails.
    """
    if not ENABLE_LOGGING:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def show_error(message: str) -> None:
    """
    Display an error message with a highlighted border and pause for 2 seconds.
    Clears the terminal after showing error to reset UX.
    """
    print(WHITE+BRIGHT+"\n" + "-"*50)
    print(LRED+f"Error: {message}")
    print(WHITE+BRIGHT+"-"*50 + "\n")
    time.sleep(2)
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass


def atomic_save(path: Path, content: str) -> None:
    """
    Save file atomically to prevent corruption:
    - Write to a temporary file first
    - Flush and fsync to ensure data is on disk
    - Replace original file safely, handling existing file conflicts
    """
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with io.open(tmp, 'w', encoding='utf-8', errors='strict') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            tmp.replace(path)
        except Exception:
            if path.exists():
                path.unlink()
            tmp.rename(path)
    except Exception as e:
        raise e

# ----- Database -----
def is_valid_user(user: dict) -> bool:
    """
    Check if a user dictionary contains all REQUIRED_FIELDS.
    Returns True if valid, else False.
    """
    return isinstance(user, dict) and REQUIRED_FIELDS.issubset(user)


def load_users() -> List[Dict]:
    """
    Load all users from all role folders.
    Skips missing or corrupted files.
    Returns a flat list of valid user dictionaries.
    """
    all_users = []
    for role in ROLES:
        file_path = DATABASE_DIR / role / USERS_FILE
        if not file_path.exists():
            continue
        try:
            with file_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for u in data:
                        if is_valid_user(u):
                            all_users.append(u)
        except json.JSONDecodeError:
            show_error(f"Corrupt JSON in {role}/{USERS_FILE}")
    return all_users

# ----- Editor -----
def open_editor(initial_text: str) -> Optional[str]:
    """
    Launch an interactive editor using prompt_toolkit.
    Supports:
    - CTRL+S: Save changes
    - CTRL+X: Cancel editing
    - CTRL+K: Cut line or selection
    - CTRL+U: Paste clipboard
    - CTRL+A: Select all text
    - CTRL+Z: Undo
    Returns edited text on save, None if cancelled or interrupted.
    """
    text_area = TextArea(
        text=initial_text,
        scrollbar=True,
        line_numbers=True,
        wrap_lines=False,
        multiline=True,
        focus_on_click=True,
    )
    status_bar = TextArea(
        text="CTRL+S Save | CTRL+X Cancel | CTRL+K Cut | CTRL+U Paste",
        height=1,
        focusable=False,
        style="class:status"
    )

    kb = KeyBindings()
    saved = {'content': None}

    # Save shortcut
    @kb.add('c-s')
    def _(event):
        saved['content'] = text_area.text
        event.app.exit()

    # Cancel shortcut
    @kb.add('c-x')
    def _(event):
        saved['content'] = None
        event.app.exit()

    # Cut shortcut
    @kb.add('c-k')
    def _(event):
        buffer = event.app.current_buffer
        if buffer.selection_state:
            buffer.cut_selection()
        else:
            doc = buffer.document
            line_start = doc.get_start_of_line_position()
            line_end = doc.get_end_of_line_position()
            start_pos = buffer.cursor_position + line_start
            end_pos = buffer.cursor_position + line_end + 1
            buffer.delete_range(start_pos, end_pos - start_pos)
            event.app.clipboard.set_data(ClipboardData(doc.current_line))

    # Paste shortcut
    @kb.add('c-u')
    def _(event):
        buffer = event.app.current_buffer
        clipboard_data = event.app.clipboard.get_data()
        if clipboard_data and clipboard_data.text:
            buffer.insert_text(clipboard_data.text)

    # Select all shortcut
    @kb.add('c-a')
    def _(event):
        buffer = event.app.current_buffer
        buffer.cursor_position = 0
        buffer.start_selection()
        buffer.cursor_position = len(buffer.text)

    # Undo shortcut
    @kb.add('c-z')
    def _(event):
        buffer = event.app.current_buffer
        buffer.undo()

    root = HSplit([Frame(text_area, title='User Editor'), status_bar])
    app = Application(layout=Layout(root), key_bindings=kb, full_screen=True)

    try:
        app.run()
    except KeyboardInterrupt:
        return None
    except Exception as e:
        show_error(f"Editor crashed: {e}")
        return None

    return saved['content']

# ----- Save -----
def save_user(user: dict) -> None:
    """
    Save or update a user in the correct role folder.
    - Creates role folder if missing
    - Updates existing user if ID matches
    - Appends new user if ID not found
    - Handles role change by removing from old role file
    - Uses atomic_save to prevent corruption
    - Logs the operation
    """
    role = user.get('role')
    if not role or role not in ROLES:
        raise ValueError("Invalid role")
    file_path = DATABASE_DIR / role / USERS_FILE
    file_path.parent.mkdir(parents=True, exist_ok=True)
    users_list = []
    if file_path.exists():
        try:
            with file_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    users_list = data
        except Exception:
            users_list = []
    updated = False
    for i, u in enumerate(users_list):
        if str(u.get('id')) == str(user.get('id')):
            users_list[i] = user
            updated = True
            break
    if not updated:
        users_list.append(user)
    atomic_save(file_path, json.dumps(users_list, ensure_ascii=False, indent=4))
    log(f"Saved user {user.get('id')} in {role}")

# ----- Validation -----
def validate_user(raw: str) -> dict:
    """
    Parse raw JSON string and validate required fields.
    Raises ValueError if JSON is invalid or missing required fields.
    Returns a validated user dictionary.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("User data must be a JSON object")
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return data

# ----- Main Loop -----
def main():
    """
    Continuous interactive loop:
    - Prompts for name, email, or ID with fuzzy search
    - Shows multiple matches for selection
    - Opens editor for the selected user
    - Saves changes and handles role transfer
    - Clears terminal and repeats until CTRL+C
    """
    while True:
        try:
            display_title()
            users = load_users()
            if not users:
                print("No users found. Check role folders and users.json.")
                time.sleep(2)
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            user_name_map = {u["name"]: u for u in users if u.get("name")}
            name_completions = list(user_name_map.keys())
            word_completer = WordCompleter(name_completions, ignore_case=True, sentence=True, match_middle=True)
            fuzzy_completer = FuzzyCompleter(word_completer)

            query = prompt("[SYSTEM] Enter name, email or ID: ",
                           style=style,
                           completer=fuzzy_completer,
                           complete_while_typing=True)

            if not query.strip():
                show_error("Empty query")
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            matches = [u for u in users if query.lower() in u.get('name', '').lower()
                                         or query.lower() in u.get('email', '').lower()
                                         or query.lower() == str(u.get('id', '')).lower()]

            if not matches:
                print("No matches found.")
                time.sleep(2)
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            if len(matches) > 1:
                print(f"Found {len(matches)} users:")
                for idx, u in enumerate(matches, 1):
                    print(f"{idx}. ID:{u['id']} Name:{u['name']} Email:{u['email']} Role:{u['role']}")
                sel = prompt("Select number to edit: ", style=style).strip()
                try:
                    idx = int(sel) - 1
                    if idx < 0 or idx >= len(matches):
                        show_error("Invalid selection")
                        os.system('cls' if os.name == 'nt' else 'clear')
                        continue
                    user = matches[idx]
                except Exception:
                    show_error("Selection parse error")
                    os.system('cls' if os.name == 'nt' else 'clear')
                    continue
            else:
                user = matches[0]

            initial_text = json.dumps(user, ensure_ascii=False, indent=4)
            edited = open_editor(initial_text)
            if not edited:
                print("Edit cancelled.")
                time.sleep(1)
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            new_user = validate_user(edited)
            old_role = user.get('role')
            new_role = new_user.get('role')

            save_user(new_user)

            if old_role != new_role and old_role in ROLES:
                old_file = DATABASE_DIR / old_role / USERS_FILE
                if old_file.exists():
                    with old_file.open('r', encoding='utf-8') as f:
                        data = json.load(f)
                    data = [u for u in data if str(u.get('id')) != str(new_user.get('id'))]
                    atomic_save(old_file, json.dumps(data, ensure_ascii=False, indent=4))

            print("User saved successfully.")
            time.sleep(2)
            os.system('cls' if os.name == 'nt' else 'clear')

        except KeyboardInterrupt:
            print("\nOperation cancelled. Exiting...")
            break
        except Exception as e:
            show_error(str(e))
            os.system('cls' if os.name == 'nt' else 'clear')
            # Loop continues


if __name__ == "__main__":
    display_title()
    main()
