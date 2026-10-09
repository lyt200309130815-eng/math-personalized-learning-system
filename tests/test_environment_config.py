"""Local dotenv loading and shared provider configuration without real API calls."""
from contextlib import closing, redirect_stdout, redirect_stderr
import io
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import settings
from database.database import get_connection
from services.llm_provider import get_provider_config, generate_text, LLMUnavailable


class EnvironmentConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env_file = self.root / '.env'
        self.fake_key = 'TEST_ONLY_NOT_A_REAL_KEY'
        self.launch_environment = {key: os.environ[key] for key in
            ('SYSTEMROOT', 'USERPROFILE', 'PATH', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP')
            if key in os.environ}
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_env(self, content=None):
        self.env_file.write_text(content or (
            'LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=' + self.fake_key +
            '\nACTIVE_TAXONOMY_VERSION=function_v2\n'), encoding='utf-8')

    def clone_database(self):
        path = self.root / 'test.db'
        with closing(get_connection(settings.PRODUCTION_DATABASE_PATH, read_only=True)) as src, \
                closing(get_connection(path)) as dst:
            src.backup(dst)
        return path

    def test_loads_supported_settings(self):
        self.write_env()
        self.assertTrue(settings.load_local_environment(self.env_file))
        self.assertEqual(os.environ['LLM_PROVIDER'], 'deepseek')
        self.assertEqual(settings.get_active_taxonomy_version(), 'function_v2')
        self.assertTrue(os.environ['DEEPSEEK_API_KEY'] == self.fake_key)
        self.assertTrue(get_provider_config()['configured'])

    def test_process_environment_wins_for_all_supported_variables(self):
        self.write_env()
        os.environ.update(LLM_PROVIDER='openai', DEEPSEEK_API_KEY='TEST_PROCESS_PLACEHOLDER',
                          ACTIVE_TAXONOMY_VERSION='geometry_v1')
        settings.load_local_environment(self.env_file)
        self.assertEqual(get_provider_config()['provider'], 'openai')
        self.assertTrue(os.environ['DEEPSEEK_API_KEY'] == 'TEST_PROCESS_PLACEHOLDER')
        self.assertEqual(settings.get_active_taxonomy_version(), 'geometry_v1')

    def test_even_empty_process_key_is_not_overridden(self):
        self.write_env()
        os.environ['DEEPSEEK_API_KEY'] = ''
        settings.load_local_environment(self.env_file)
        self.assertFalse(get_provider_config()['configured'])

    def test_default_path_is_project_root_not_current_directory(self):
        self.write_env()
        with patch.object(settings, 'PROJECT_ROOT', self.root):
            settings.load_local_environment()
        self.assertTrue(get_provider_config()['configured'])

    def test_missing_file_keeps_system_configuration_and_starts(self):
        self.assertFalse(settings.load_local_environment(self.env_file))
        self.assertEqual(settings.get_active_taxonomy_version(), 'function_v2')
        self.assertEqual(get_provider_config()['provider'], 'deepseek')
        self.assertFalse(get_provider_config()['configured'])
        os.environ['DEEPSEEK_API_KEY'] = self.fake_key
        settings.load_local_environment(self.env_file)
        self.assertTrue(get_provider_config()['configured'])

    def test_unreadable_file_is_silent(self):
        with patch('settings.load_dotenv', side_effect=PermissionError(self.fake_key)):
            self.assertFalse(settings.load_local_environment(self.env_file))

    def test_loading_and_provider_failure_do_not_expose_key(self):
        self.write_env()
        output, errors, logs = io.StringIO(), io.StringIO(), io.StringIO()
        handler = logging.StreamHandler(logs)
        logger = logging.getLogger()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        with redirect_stdout(output), redirect_stderr(errors):
            settings.load_local_environment(self.env_file)
            config = get_provider_config()
            with patch.dict('services.llm_provider.PROVIDER_GENERATORS',
                            {'deepseek': lambda *args: (_ for _ in ()).throw(RuntimeError(self.fake_key))}):
                try:
                    generate_text('测试反馈')
                except LLMUnavailable:
                    traceback.print_exc(file=errors)
                else:
                    self.fail('Expected a sanitized provider failure')
        self.assertNotIn(self.fake_key, output.getvalue() + errors.getvalue() + logs.getvalue() + str(config))

    def test_fresh_import_auto_loads_when_launched_outside_project(self):
        # Stage settings with a fake .env so no real local credential enters tests.
        (self.root / 'settings.py').write_text(Path(settings.__file__).read_text(encoding='utf-8'), encoding='utf-8')
        self.write_env()
        elsewhere = self.root / 'shortcut_working_directory'
        elsewhere.mkdir()
        code = (
            'import sys,os;sys.path.insert(0,sys.argv[1]);import settings;'
            'assert os.environ.get("LLM_PROVIDER")=="deepseek";'
            'assert os.environ.get("DEEPSEEK_API_KEY")=="TEST_ONLY_NOT_A_REAL_KEY";'
            'assert settings.get_active_taxonomy_version()=="function_v2";print("PASS")'
        )
        result = subprocess.run([sys.executable, '-c', code, str(self.root)], cwd=elsewhere,
                                capture_output=True, text=True, timeout=30, env=self.launch_environment)
        self.assertEqual(result.returncode, 0, 'Fresh configuration bootstrap failed')
        self.assertEqual(result.stdout.strip(), 'PASS')
        self.assertNotIn(self.fake_key, result.stdout + result.stderr)

    def test_function_and_geometry_share_one_dotenv_provider(self):
        self.write_env()
        settings.load_local_environment(self.env_file)
        path = self.clone_database()
        with patch.dict(os.environ, {'MATH_AI_DATABASE_PATH': str(path)}), \
                patch.dict('services.llm_provider.PROVIDER_GENERATORS', {'deepseek': lambda *args: '模拟反馈'}):
            for version in ('function_v2', 'geometry_v1'):
                os.environ['ACTIVE_TAXONOMY_VERSION'] = version
                self.assertEqual(get_provider_config()['provider'], 'deepseek')
                self.assertEqual(generate_text('测试'), '模拟反馈')
                app = AppTest.from_file(str(settings.PROJECT_ROOT / 'pages/feedback.py')).run()
                self.assertFalse(app.exception)
                self.assertTrue(any('DeepSeek' in item.value for item in app.markdown))
                visible = str(app.markdown) + str(app.info) + str(app.warning) + str(app.exception)
                self.assertNotIn(self.fake_key, visible)

    def test_missing_dotenv_feedback_page_for_both_topics(self):
        path = self.clone_database()
        settings.load_local_environment(self.env_file)
        with patch.dict(os.environ, {'MATH_AI_DATABASE_PATH': str(path)}):
            for version in ('function_v2', 'geometry_v1'):
                os.environ['ACTIVE_TAXONOMY_VERSION'] = version
                app = AppTest.from_file(str(settings.PROJECT_ROOT / 'pages/feedback.py')).run()
                self.assertFalse(app.exception)
                self.assertTrue(any('DeepSeek尚未配置' in item.value for item in app.info))
                self.assertTrue(app.button[0].disabled)
                app.button[1].click().run()
                self.assertFalse(app.exception)
                self.assertIsNotNone(app.session_state['learning_feedback'])

    def test_example_and_gitignore_are_safe(self):
        example = (settings.PROJECT_ROOT / '.env.example').read_text(encoding='utf-8')
        self.assertEqual(example.strip(), 'DEEPSEEK_API_KEY=')
        self.assertIn('.env', (settings.PROJECT_ROOT / '.gitignore').read_text(encoding='utf-8').splitlines())


if __name__ == '__main__':
    unittest.main()
