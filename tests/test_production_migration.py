"""Production-path opt-in and rollback tests use disposable databases only."""
from contextlib import closing
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from database.database import get_connection, record_attempt
from database.taxonomy_migration import migrate_function_v2, protected_snapshot
from init_db import initialize_database
from scripts.function_v2_dry_run import load_gold
from scripts.migrate_function_v2 import run_migration


class ProductionMigrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'production.db'
        initialize_database(self.path)
        record_attempt('TEST', 'Q001', 'D', 1, 2., database_path=self.path, taxonomy_version='function_v1')
        self.gold = load_gold()

    def snapshot(self):
        with closing(get_connection(self.path, read_only=True)) as conn:
            return protected_snapshot(conn)

    def test_explicit_production_migration_preserves_history_and_is_idempotent(self):
        before = self.snapshot()
        with patch('database.taxonomy_migration.DATABASE_PATH', self.path):
            with self.assertRaises(ValueError):
                migrate_function_v2(self.path, self.gold)
            self.assertEqual(migrate_function_v2(self.path, self.gold, allow_production=True), {'inserted': 66, 'skipped': 0})
            after = self.snapshot()
            self.assertEqual(after['attempts_digest'], before['attempts_digest'])
            self.assertEqual(after['attempts_count'], before['attempts_count'])
            self.assertEqual(migrate_function_v2(self.path, self.gold, allow_production=True), {'inserted': 0, 'skipped': 66})
            self.assertEqual(self.snapshot(), after)
        with closing(get_connection(self.path, read_only=True)) as conn:
            self.assertEqual(conn.execute("SELECT status FROM taxonomy_versions WHERE version='function_v2'").fetchone()[0], 'active')

    def test_accidental_attempt_mutation_rolls_back_all_schema_and_data(self):
        before = self.snapshot()
        from database.taxonomy_migration import _insert_mapping
        def corrupt(conn, *args):
            _insert_mapping(conn, *args)
            conn.execute('UPDATE attempts SET is_correct=0')
        with patch('database.taxonomy_migration._insert_mapping', side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, 'attempts'):
                migrate_function_v2(self.path, self.gold, allow_production=True)
        self.assertEqual(self.snapshot(), before)
        with closing(get_connection(self.path, read_only=True)) as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_catalog'").fetchone())

    def test_unapproved_input_rejected_without_schema_changes(self):
        before = self.snapshot()
        for status in ('draft', 'reviewed', 'rejected'):
            rows = [dict(q) for q in self.gold]
            rows[0]['quality_status'] = status
            with self.assertRaises(ValueError):
                migrate_function_v2(self.path, rows, allow_production=True)
        self.assertEqual(self.snapshot(), before)

    def test_cli_records_absolute_path_counts_and_digest(self):
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()):
            report = run_migration(self.path, self.path.parent / 'report.json')
        self.assertEqual(report['before']['database_path'], str(self.path.resolve()))
        self.assertEqual(report['before']['attempts_digest'], report['after']['attempts_digest'])
        self.assertEqual(report['before']['attempts_count'], report['after']['attempts_count'])

    def test_default_runtime_v2_and_explicit_v1_override(self):
        import os
        from settings import get_active_taxonomy_version
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_active_taxonomy_version(), 'function_v2')
        with patch.dict(os.environ, {'ACTIVE_TAXONOMY_VERSION': 'function_v1'}):
            self.assertEqual(get_active_taxonomy_version(), 'function_v1')
