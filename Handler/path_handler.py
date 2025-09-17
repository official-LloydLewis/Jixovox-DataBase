from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # Points to JIXOVOX
DATABASE_DIR = BASE_DIR / 'Database'

DATA_FILE = DATABASE_DIR / 'data.json'
