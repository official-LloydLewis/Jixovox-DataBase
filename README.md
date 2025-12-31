---

# 📂 JIXOVOX-DATABASE (v1.0)

A modular **user and bot database management system** with secure authentication, CLI utilities, and role-based organization.
The project provides tools for **adding, searching, updating, removing, and logging users** while ensuring **security, scalability, and usability**.

---

## 🚀 Features

* **Secure User Management**

  * Password hashing with **Argon2** + per-user salt + global pepper.
  * Fernet encryption for sensitive fields.
  * Strict validation (strong passwords, valid emails, unique IDs).

* **Role-Based Organization**

  * Users stored in role-specific directories:

    * `Owner/`, `Developer/`, `Admin/`, `Member/`, `Bot/`.

* **Bot Account Generator**

  * Automated bot creation with unique names, emails, and random secure passwords.

* **CLI Utilities**

  * Interactive prompts with **prompt\_toolkit** (autocomplete, colored UI, keyboard shortcuts).
  * Search with **fuzzy matching** (via rapidfuzz).
  * Real-time **log viewer** with watchdog support.

* **Robust Database Handling**

  * JSONL + gzip for efficient storage.
  * Append-only and full-save modes.
  * Thread-safe operations with caching.

* **Logging & Stats**

  * Rotating log files for actions.
  * Statistics of users maintained in `stats.json`.

---

## 📂 Project Structure

```
JIXOVOX-DATABASE/
│
├── Database/                # Main database (role-based folders)
│   ├── Admin/
│   ├── Bot/
│   ├── Developer/
│   ├── Logs/
│   ├── Member/
│   └── Owner/
│   ├── add.py               # Add/register a new user securely
│   ├── bot_creator.py       # Automated bot account generator
│   ├── log_display.py       # Real-time log monitoring
│   ├── remove.py            # Remove users from database
│   ├── search.py            # Search users (with fuzzy search support)
│   ├── update.py            # Full-screen interactive user editor
│   └── USERS.py             # Core Users class (CRUD operations, validation)
│
├── Handler/
│   └── path_handler.py      # Centralized path management
│
├── Utils/
│   ├── colors.py            # Colored CLI output
│   └── display_title.py     # Styled CLI titles
│
├── .gitignore
└── .gitattributes
```

---

## ⚙️ Installation

```bash
# Clone the repo
git clone https://github.com/your-username/JIXOVOX-DATABASE.git
cd JIXOVOX-DATABASE

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux / Mac
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## 📦 Dependencies

* `argon2-cffi` → password hashing
* `cryptography` → Fernet encryption
* `prompt_toolkit` → interactive CLI
* `rapidfuzz` → fuzzy search
* `watchdog` → real-time log monitoring

---

## 🖥️ Usage

### ➕ Add a user

```bash
python Database/add.py
```

### 🤖 Create bots

```bash
python Database/bot_creator.py
```

### 🔍 Search users

```bash
python Database/search.py
```

### ✏️ Update user

```bash
python Database/update.py
```

### ❌ Remove user

```bash
python Database/remove.py
```

### 📑 View logs

```bash
python Database/log_display.py
```

### 🧭 Unified CLI entrypoint

```bash
python Database/cli.py --help
python Database/cli.py add
python Database/cli.py export
python Database/cli.py backup --retention 5
```

---

## 🔐 Security Highlights

* Strong password policy (min 8 chars, mixed case, number, special char).
* Multi-layered hashing (Argon2 + salt + pepper).
* Encrypted storage for sensitive data.
* Duplicate prevention on email and username.
* Brute force protection (limited login attempts).

---

## 📌 Roadmap / Improvements

* [x] Unified CLI entrypoint that wraps add/search/update/remove/export tasks.
* [x] Automated backup workflow with retention (foundation for scheduling).
* [x] End-to-end test suite covering export/import flows and data integrity checks.
* [x] Configuration system (env file + overrides) for paths, keys, and limits.
* [ ] Developer docs for extending roles and integrating with other apps.

---
## 📜 License

**License: None**  
This project is **not licensed for public use or redistribution**.  
_All Rights Reserved By The Author._

---
## 📬 Contact

If you have new ideas, suggestions, or want to get in touch:

* **Email**: [lloydlewizzz@gmail.com](mailto:lloydlewizzz@gmail.com)
* **Discord**: `lloydlewizzz`

---
