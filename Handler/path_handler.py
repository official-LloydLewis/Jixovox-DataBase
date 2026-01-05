# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # Points to JIXOVOX
DATABASE_DIR = BASE_DIR / 'Database'

DATA_FILE = DATABASE_DIR / 'data.json'
