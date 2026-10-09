"""Cloud configuration and clean deployment-bank regression checks."""
import os
import unittest
from contextlib import closing
from unittest.mock import patch
import streamlit as st
import settings
from database.database import get_connection, get_training_questions
from services.question_assets import readable_asset

class CloudDeploymentTests(unittest.TestCase):
    def test_secrets_override_dotenv_but_environment_wins(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'local'}, clear=True), patch.dict(settings._DOTENV_INSERTED, {'LLM_PROVIDER': 'local'}, clear=True), patch.object(st, 'secrets', {'LLM_PROVIDER': 'deepseek'}):
            self.assertEqual(settings.get_setting('LLM_PROVIDER'), 'deepseek')
            os.environ['LLM_PROVIDER'] = 'openai'
            self.assertEqual(settings.get_setting('LLM_PROVIDER'), 'openai')

    def test_missing_secrets_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(st, 'secrets', {}):
            self.assertEqual(settings.get_setting('NOT_CONFIGURED', 'default'), 'default')

    def test_seed_has_no_student_records_and_both_topics(self):
        path = settings.PROJECT_ROOT / 'data/deployment/question_bank.db'
        with closing(get_connection(path, read_only=True)) as conn:
            for table in ('attempts', 'diagnostic_sessions', 'training_sessions', 'subjective_submissions', 'answer_review_requests'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        for version in ('function_v2', 'geometry_v1'):
            questions = get_training_questions(path, taxonomy_version=version)
            self.assertTrue(questions)
            for question in questions:
                for asset in question.get('diagram_assets', []):
                    self.assertTrue(readable_asset(asset))
                    self.assertNotIn('\\', asset['path'])
                    parent = settings.PROJECT_ROOT
                    for part in asset['path'].split('/'):
                        self.assertIn(part, [item.name for item in parent.iterdir()])
                        parent = parent / part

    def test_database_url_is_explicitly_sqlite_only(self):
        with patch('settings.get_setting', return_value='postgresql://placeholder'):
            with self.assertRaises(ValueError):
                settings.get_database_path()
