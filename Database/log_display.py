# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
# Log Editor CLI with live file watching and advanced key bindings
"""
A terminal-based log editor with:
- Real-time file monitoring using Watchdog
- Full editing capabilities (cut, copy, paste, undo, select all)
- Internal clipboard management
- Safe atomic file save with encoding handling
- Cross-platform support (Windows/Unix)
- Status bar with temporary messages
- Fallbacks and error handling for missing packages
"""

import sys
import os
import io
import threading
from pathlib import Path
import time

# ---------- Optional Imports with Fallbacks ----------
try:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit
    from prompt_toolkit.widgets import TextArea, Frame
    from prompt_toolkit.styles import Style
    from prompt_toolkit.selection import SelectionState, SelectionType
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError as e:
    print(f"Missing required package: {e.name}. Install via pip (e.g., pip install prompt_toolkit watchdog).")
    sys.exit(1)

# ---------- Paths & Constants ----------
def _safe_base_dir() -> Path:
    """Get current script directory or fallback to cwd."""
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return Path.cwd()

BASE_DIR: Path = _safe_base_dir()
LOGS_DIR: Path = BASE_DIR / "Logs"
LOG_FILE: Path = LOGS_DIR / "system_log.txt"

# Style configuration for prompt_toolkit
style = Style.from_dict({
    "text-area": "bg:#111111 fg:#ffffff",
    "status": "reverse",
})

clipboard = ""  # Internal clipboard

# ---------- Utility Functions ----------
def show_error(message: str) -> None:
    """Display error message and clear screen."""
    print("\n" + "-" * 60)
    print(f"Error: {message}")
    print("-" * 60 + "\n")
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass

def ensure_log_file() -> None:
    """Ensure log directory and file exist."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            LOG_FILE.write_text("", encoding="utf-8")
    except Exception as e:
        show_error(f"Failed to prepare log file: {e}")

def load_file() -> str:
    """Load file content safely with encoding fallback."""
    ensure_log_file()
    try:
        with io.open(LOG_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with io.open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        show_error(f"Could not read file: {e}")
        return ""

def atomic_save(path: Path, content: str) -> None:
    """Atomically save content to a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with io.open(tmp, "w", encoding="utf-8", errors="strict") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    try:
        tmp.replace(path)
    except Exception:
        if path.exists():
            path.unlink()
        tmp.rename(path)

def save_file(content: str) -> None:
    """Save content safely with error handling."""
    ensure_log_file()
    try:
        atomic_save(LOG_FILE, content)
    except PermissionError:
        show_error("Permission denied while saving.")
    except Exception as e:
        show_error(f"Could not save file: {e}")

# ---------- Watchdog Handler ----------
class LogHandler(FileSystemEventHandler):
    """Watchdog handler to auto-refresh text area on file changes."""
    def __init__(self, text_area: TextArea):
        self.text_area = text_area
        self._lock = threading.Lock()

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        # Cross-platform path comparison
        if os.path.abspath(event.src_path) == str(LOG_FILE.resolve()):
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    new_content = f.read()
                with self._lock:
                    self.text_area.buffer.text = new_content
            except Exception:
                pass

def start_watchdog(text_area: TextArea) -> None:
    """Start the Watchdog observer thread."""
    event_handler = LogHandler(text_area)
    observer = Observer()
    observer.schedule(event_handler, str(LOGS_DIR), recursive=False)
    observer.daemon = True
    observer.start()

# ---------- Main Application ----------
def main() -> None:
    """Main entry point for the log editor CLI."""
    global clipboard

    # Text area for editing logs
    text_area = TextArea(
        text=load_file(),
        scrollbar=True,
        line_numbers=True,
        wrap_lines=False,
        multiline=True,
        style="class:text-area",
    )

    # Status bar
    status_bar = TextArea(
        text=(
            "CTRL+S Save | CTRL+X Exit | CTRL+K Cut | CTRL+U Paste | "
            "SHIFT+Arrow Select | CTRL+A Select All | CTRL+Z Undo | DEL Delete"
        ),
        height=1,
        style="class:status",
        focusable=False,
    )

    kb = KeyBindings()

    # ---------- File Operations ----------
    @kb.add("c-s")
    def _(event) -> None:
        save_file(text_area.text)
        # Show temporary "Saved!" message in status bar
        original = status_bar.text
        status_bar.text = "Saved!"
        def clear_status():
            time.sleep(2)
            status_bar.text = original
        threading.Thread(target=clear_status, daemon=True).start()

    @kb.add("c-x")
    def _(event) -> None:
        event.app.exit()

    # ---------- Clipboard Operations ----------
    @kb.add("c-k")
    def _(event) -> None:
        global clipboard
        buffer = text_area.buffer
        if buffer.selection_state:
            data = buffer.cut_selection()
            clipboard = data.text if data else ""
        else:
            lines = buffer.text.splitlines()
            if not lines:
                return
            row = buffer.document.cursor_position_row
            row = max(0, min(row, len(lines) - 1))
            clipboard = lines[row]
            del lines[row]
            buffer.text = "\n".join(lines)
            try:
                new_idx = buffer.document.translate_row_col_to_index(
                    min(row, len(lines) - 1) if lines else 0, 0
                )
                buffer.cursor_position = new_idx
            except Exception:
                buffer.cursor_position = 0

    @kb.add("c-u")
    def _(event) -> None:
        global clipboard
        buffer = text_area.buffer
        lines = buffer.text.splitlines()
        row = buffer.document.cursor_position_row
        row = max(0, min(row, len(lines)))
        insert_text = clipboard or ""
        if not lines:
            lines = [insert_text]
            new_row = 0
        else:
            lines.insert(row, insert_text)
            new_row = row
        buffer.text = "\n".join(lines)
        try:
            new_idx = buffer.document.translate_row_col_to_index(new_row, 0)
            buffer.cursor_position = new_idx
        except Exception:
            buffer.cursor_position = len(buffer.text)

    @kb.add("c-c")
    def _(event) -> None:
        global clipboard
        buffer = text_area.buffer
        if buffer.selection_state:
            data = buffer.copy_selection()
            clipboard = data.text if data else ""

    # ---------- Undo ----------
    @kb.add("c-z")
    def _(event) -> None:
        try:
            text_area.buffer.undo()
        except Exception as e:
            show_error(f"Undo failed: {e}")

    # ---------- Select All ----------
    @kb.add("c-a")
    def _(event) -> None:
        buffer = text_area.buffer
        buffer.selection_state = SelectionState(
            original_cursor_position=0, type=SelectionType.CHARACTERS
        )
        buffer.cursor_position = len(buffer.text)

    # ---------- Delete / Backspace ----------
    @kb.add("delete")
    def _(event) -> None:
        buffer = text_area.buffer
        if buffer.selection_state:
            buffer.cut_selection()
            return
        lines = buffer.text.splitlines()
        if not lines:
            return
        row = buffer.document.cursor_position_row
        row = max(0, min(row, len(lines) - 1))
        del lines[row]
        buffer.text = "\n".join(lines)
        if lines:
            new_row = min(row, len(lines) - 1)
            try:
                new_idx = buffer.document.translate_row_col_to_index(new_row, 0)
                buffer.cursor_position = new_idx
            except Exception:
                buffer.cursor_position = len(buffer.text)
        else:
            buffer.cursor_position = 0

    @kb.add("backspace")
    def _(event) -> None:
        buffer = text_area.buffer
        if buffer.selection_state:
            buffer.cut_selection()
        else:
            buffer.delete_before_cursor(count=1)

    # ---------- Shift + Arrows for Selection ----------
    @kb.add("s-left")
    def _(event) -> None:
        buffer = text_area.buffer
        if buffer.selection_state is None:
            buffer.start_selection(selection_type=SelectionType.CHARACTERS)
        buffer.cursor_left(count=1)

    @kb.add("s-right")
    def _(event) -> None:
        buffer = text_area.buffer
        if buffer.selection_state is None:
            buffer.start_selection(selection_type=SelectionType.CHARACTERS)
        buffer.cursor_right(count=1)

    @kb.add("s-up")
    def _(event) -> None:
        buffer = text_area.buffer
        doc = buffer.document
        if doc.cursor_position_row > 0:
            target_row = doc.cursor_position_row - 1
            target_index = doc.translate_row_col_to_index(
                target_row, min(doc.cursor_position_col, len(doc.lines[target_row]))
            )
            if buffer.selection_state is None:
                buffer.start_selection(selection_type=SelectionType.CHARACTERS)
            buffer.cursor_position = target_index

    @kb.add("s-down")
    def _(event) -> None:
        buffer = text_area.buffer
        doc = buffer.document
        if doc.cursor_position_row < len(doc.lines) - 1:
            target_row = doc.cursor_position_row + 1
            target_index = doc.translate_row_col_to_index(
                target_row, min(doc.cursor_position_col, len(doc.lines[target_row]))
            )
            if buffer.selection_state is None:
                buffer.start_selection(selection_type=SelectionType.CHARACTERS)
            buffer.cursor_position = target_index

    # ---------- Arrow Up/Down clears selection ----------
    @kb.add("up")
    def _(event) -> None:
        buffer = text_area.buffer
        if buffer.selection_state:
            buffer.exit_selection()
        buffer.cursor_up(count=1)

    @kb.add("down")
    def _(event) -> None:
        buffer = text_area.buffer
        if buffer.selection_state:
            buffer.exit_selection()
        buffer.cursor_down(count=1)

    # ---------- Layout & Application ----------
    root_container = HSplit([Frame(text_area, title="System Log Editor"), status_bar])

    app = Application(
        layout=Layout(root_container),
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,
        style=style,
    )

    # Start watchdog thread for live updates
    start_watchdog(text_area)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        show_error(f"App crashed: {e}")

if __name__ == "__main__":
    main()
