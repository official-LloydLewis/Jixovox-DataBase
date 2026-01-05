# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from Handler.config_loader import load_config
from Database import export_import


class ExportImportTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_root = Path(self.tempdir.name) / "Database"
        self.db_root.mkdir(parents=True, exist_ok=True)

        # Prepare role folders with baseline data
        for role in export_import.DEFAULT_ROLES:
            role_dir = self.db_root / role
            role_dir.mkdir(parents=True, exist_ok=True)
            (role_dir / export_import.USER_FILE).write_text("[]", encoding="utf-8")

        self.config = load_config(
            overrides={
                "PROJECT_ROOT": self.tempdir.name,
                "DATABASE_DIR": str(self.db_root),
                "EXPORTS_DIR": str(self.db_root / "data" / "exports"),
                "STATS_FILE": str(self.db_root / "Logs" / "stats.json"),
                "BACKUP_RETENTION": "2",
            }
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _write_sample_users(self):
        owners = [
            {"id": "1", "name": "OwnerOne", "email": "owner1@example.com", "role": "Owner"},
            {"id": "2", "name": "OwnerTwo", "email": "owner2@example.com", "role": "Owner"},
        ]
        owner_file = self.db_root / "Owner" / export_import.USER_FILE
        owner_file.write_text(json.dumps(owners), encoding="utf-8")

    def test_export_and_import_roundtrip(self):
        self._write_sample_users()
        snapshot = export_import.export_database(config=self.config)
        self.assertTrue(snapshot.exists())

        # Replace data with a smaller set
        snapshot_data = json.loads(snapshot.read_text(encoding="utf-8"))
        snapshot_data["users"]["Owner"] = [
            {"id": "10", "name": "NewOwner", "email": "new@example.com", "role": "Owner"}
        ]
        snapshot.write_text(json.dumps(snapshot_data), encoding="utf-8")

        summary = export_import.import_database(snapshot, mode="replace", config=self.config)
        self.assertEqual(summary.roles_updated["Owner"], 1)

        owner_file = self.db_root / "Owner" / export_import.USER_FILE
        current = json.loads(owner_file.read_text(encoding="utf-8"))
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["name"], "NewOwner")

    def test_backup_prunes_exports(self):
        export_import.run_backup(config=self.config, retention=1)
        export_import.run_backup(config=self.config, retention=1)
        export_import.run_backup(config=self.config, retention=1)

        exports = sorted((self.db_root / "data" / "exports").glob("users-export-*.json"))
        self.assertLessEqual(len(exports), 1)


if __name__ == "__main__":
    unittest.main()
