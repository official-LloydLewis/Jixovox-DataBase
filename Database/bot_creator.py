# Database/bot_creator.py
"""
Secure automated bot account generator with:
- Random unique bot name and email generation
- Strong random password assignment with SHA-256 hashing
- JSON database storage with automatic file creation
- Logging of every bot creation event and total count
- Input validation with upper bound to prevent abuse
- Fallback for colors and display_title if Utils is missing
- Colorized CLI output for better readability
- Clear error messages and input validation
- Cross-platform console clear and UTF-8 encoding
- Full type hints for better readability and IDE support
"""

import os
import sys
import time
import json
import logging
import random
import string
import hashlib
from pathlib import Path
from typing import Dict, List, Set

# ==========================================================
# Optional Imports with Fallbacks
# ==========================================================
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from Handler.path_handler import DATABASE_DIR
except Exception:
    # Fallback database directory if Handler.path_handler is missing
    DATABASE_DIR = Path(__file__).resolve().parent / "Database"
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

try:
    from Utils.colors import WHITE, BRIGHT, LRED, GREEN, BLUE, RESET
except Exception:
    # Simple fallback: disable colors
    WHITE = BRIGHT = LRED = GREEN = BLUE = RESET = ""

try:
    from Utils.display_title import display_title
except Exception:
    def display_title(title: str) -> None:
        print(f"\n{title}\n" + "=" * len(title))

# ==========================================================
# Path Configuration
# ==========================================================
BASE_DIR: Path = Path(__file__).resolve().parent
BOT_DIR: Path = DATABASE_DIR / "Bot"
BOT_FILE: Path = BOT_DIR / "users.json"
LOG_FILE: Path = BASE_DIR / "Logs" / "system_log.txt"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
BOT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================================
# Logger Configuration
# ==========================================================
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# ==========================================================
# Helper Functions
# ==========================================================

def show_loading(message: str = "Processing") -> None:
    """Display a simple loading animation."""
    print(f"\n{WHITE}{message}", end='', flush=True)
    for _ in range(3):
        print(".", end='', flush=True)
        time.sleep(0.5)
    print("\n")

def show_error(message: str) -> None:
    """Print a formatted error message and pause briefly."""
    logging.error(f"Error: {message}")
    print(WHITE + BRIGHT + "\n" + "-" * 40)
    print(LRED + BRIGHT + f"Error: {message}")
    print(WHITE + BRIGHT + "-" * 40 + "\n")
    time.sleep(2)

def log_action(bot: Dict[str, str]) -> None:
    """Log creation of a single bot."""
    logging.info(f"Created bot '{bot['name']}' with email '{bot['email']}'")

def load_bots() -> List[Dict[str, str]]:
    """Load existing bots from the JSON file. Create file if missing."""
    if not BOT_FILE.exists():
        BOT_FILE.write_text("[]", encoding="utf-8")
    try:
        with open(BOT_FILE, "r", encoding="utf-8") as f:
            bots: List[Dict[str, str]] = json.load(f)
            logging.info("Loaded %d existing bots from database", len(bots))
            return bots
    except json.JSONDecodeError as e:
        logging.error("JSON decode error: %s", e)
        return []

def save_bots(bots: List[Dict[str, str]]) -> None:
    """Save the full bot list to the JSON file."""
    with open(BOT_FILE, "w", encoding="utf-8") as f:
        json.dump(bots, f, indent=4)
    logging.info("Saved total %d bots to database", len(bots))

# ==========================================================
# Bot Creation Helpers
# ==========================================================

def generate_unique_name(existing_names: Set[str]) -> str:
    """Generate a unique bot name."""
    while True:
        name = "Bot" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if name not in existing_names:
            return name

def generate_unique_email(existing_emails: Set[str]) -> str:
    """Generate a unique bot email."""
    while True:
        prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        email = f"{prefix}@botmail.com"
        if email not in existing_emails:
            return email

def hash_password(password: str) -> str:
    """Return a SHA-256 hash of the password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def create_bots(count: int) -> List[Dict[str, str]]:
    """
    Create the requested number of bots,
    ensuring unique names and emails,
    and save them to the database.
    """
    bots: List[Dict[str, str]] = load_bots()
    existing_names: Set[str] = {b["name"] for b in bots}
    existing_emails: Set[str] = {b["email"] for b in bots}

    new_bots: List[Dict[str, str]] = []
    for _ in range(count):
        name = generate_unique_name(existing_names)
        email = generate_unique_email(existing_emails)
        password_plain = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        password_hashed = hash_password(password_plain)

        bot = {
            "name": name,
            "email": email,
            "password_hash": password_hashed,
            "role": "Bot"
        }

        bots.append(bot)
        new_bots.append(bot)
        existing_names.add(name)
        existing_emails.add(email)
        log_action(bot)

    save_bots(bots)
    logging.info("Created %d new bots in this session", len(new_bots))
    return new_bots

# ==========================================================
# Main CLI
# ==========================================================

def main() -> None:
    """CLI entry point for creating bot accounts."""
    display_title("Bot Creator")
    try:
        raw = input(f"{WHITE + BRIGHT}How many bots do you want to create? (1-1000) {RESET}").strip()
        count = int(raw)
        if count <= 0 or count > 1000:
            show_error("Please enter a number between 1 and 1000.")
            return

        show_loading("Creating bots")
        new_bots = create_bots(count)

        print(f"{GREEN + BRIGHT}{len(new_bots)} bots successfully created and saved to Bot/users.json{RESET}\n")

        header = f"{WHITE + BRIGHT}{'Id'.ljust(5)}{'Name'.ljust(18)}{'Email'}{RESET}"
        print(header)
        for i, bot in enumerate(new_bots, 1):
            id_str = f"{WHITE + BRIGHT}{str(i).ljust(5)}"
            name_str = f"{BLUE + BRIGHT}{bot['name'].ljust(18)}"
            email_str = f"{BLUE}{bot['email']}"
            print(f"{id_str}{name_str}{email_str}")

    except ValueError:
        show_error("Please enter a valid number.")

# ==========================================================
# Script Execution
# ==========================================================
if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    main()
