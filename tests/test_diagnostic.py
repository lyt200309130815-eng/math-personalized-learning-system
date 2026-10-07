"""Offline assessment lifecycle, adaptation and real Streamlit navigation."""
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.database import get_connection, get_training_questions
from database.taxonomy_migration import migrate_function_v2
from init_db import initialize_database
from scripts.function_v2_dry_run import load_gold
from services.diagnostic import generate_diagnostic_test, start_diagnostic, submit_diagnostic_answer, restore_diagnostic
from services.mastery import calculate_student_mastery

ROOT = Path(__file__).resolve().parents[1]


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'assessment.db'
        initialize_database(self.path)
        migrate_function_v2(self.path, load_gold())
        self.env = patch.dict(os.environ, {'MATH_AI_DATABASE_PATH': str(self.path),
            'ACTIVE_TAXONOMY_VERSION': 'function_v2', 'OPENAI_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'GEMINI_API_KEY': ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def submit(self, state, correct=True):
        q = state['current_question']
        answer = q['answer'] if correct else next(c for c in 'ABCD' if c != q['answer'])
        return submit_diagnostic_answer(state['id'], q['id'], answer, answer_time=2.)

    def complete(self, student='NEW', correct=True):
        state = start_diagnostic(student)
        while not state['diagnostic_completed']:
            state = self.submit(state, correct)
        return state

    def count_attempts(self):
        with closing(get_connection(self.path, read_only=True)) as conn:
            return conn.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]

    def test_new_student_deterministic_pool_and_first_question(self):
        a, b = generate_diagnostic_test('NEW'), generate_diagnostic_test('NEW')
        self.assertEqual(a['pool'], b['pool'])
        self.assertEqual(a['current_question'], b['current_question'])
        self.assertEqual(a['current_question']['knowledge_point_id'], 'K001')
        self.assertEqual(a['max_questions'], 18)
        self.assertTrue(all(q['difficulty'] <= 3 for q in a['pool']))
        self.assertEqual(self.count_attempts(), 0)

    def test_only_approved_excludes_all_three_other_statuses(self):
        for status in ('reviewed', 'draft', 'rejected'):
            with closing(get_connection()) as conn, conn:
                conn.execute("UPDATE question_knowledge_mappings SET review_status=? WHERE question_id='Q001'", (status,))
            self.assertNotIn('Q001', {q['id'] for q in generate_diagnostic_test('NEW')['pool']})

    def test_no_data_is_none(self):
        profile = calculate_student_mastery('NEW')
        self.assertEqual(len(profile), 15)
        self.assertTrue(all(p['mastery_score'] is None for p in profile))

    def test_atomic_attempt_link_and_duplicate_submission(self):
        state = start_diagnostic('NEW')
        q = state['current_question']
        saved = self.submit(state)
        repeat = submit_diagnostic_answer(state['id'], q['id'], q['answer'])
        self.assertEqual(saved['answers'], repeat['answers'])
        self.assertEqual(self.count_attempts(), 1)
        with closing(get_connection(read_only=True)) as conn:
            link = conn.execute('SELECT * FROM diagnostic_answers').fetchone()
            self.assertEqual(link['attempt_mode'], 'diagnostic')
            attempt = conn.execute('SELECT * FROM attempts').fetchone()
            self.assertEqual(attempt['student_id'], 'NEW')
            self.assertEqual(attempt['is_correct'], 1)
            self.assertEqual(attempt['answer_time'], 2.)

    def test_completion_fifteen_node_snapshot_recommendation_unique_questions(self):
        state = self.complete()
        self.assertEqual(state['result']['total'], 18)
        self.assertEqual(len(state['result']['profile']), 15)
        self.assertEqual(len({a['question_id'] for a in state['answers']}), 18)
        self.assertEqual(state['result']['recommendation']['status'], 'ready')
        self.assertEqual(len({a['knowledge_point_id'] for a in state['answers']}), 15)

    def test_completed_view_and_explicit_restart(self):
        completed = self.complete()
        self.assertEqual(restore_diagnostic('NEW'), completed)
        self.assertEqual(start_diagnostic('NEW')['id'], completed['id'])
        new = start_diagnostic('NEW', restart=True)
        self.assertNotEqual(new['id'], completed['id'])
        self.assertEqual(new['answers'], [])
        self.assertEqual(self.count_attempts(), 18)
        self.assertEqual(start_diagnostic('NEW')['id'], new['id'])

    def test_refresh_restores_current_question_and_timer(self):
        state = self.submit(start_diagnostic('NEW'))
        self.assertEqual(restore_diagnostic('NEW'), state)
        self.assertEqual(start_diagnostic('NEW'), state)
        self.assertEqual(self.count_attempts(), 1)

    def test_prerequisite_failure_demotes_advanced_but_retains_breadth(self):
        bad = start_diagnostic('BAD')
        for _ in range(4):
            bad = self.submit(bad, False)
        self.assertNotIn(bad['current_question']['knowledge_point_id'], ('K010', 'K011', 'K014'))
        while not bad['diagnostic_completed']:
            bad = self.submit(bad, False)
        tested = {a['knowledge_point_id'] for a in bad['answers']}
        self.assertGreaterEqual(len(tested), 12)
        target = bad['result']['recommendation']['target_knowledge']
        self.assertIn(target['knowledge_point_id'], ('K001', 'K002'))

    def test_missing_node_questions_does_not_crash(self):
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='draft' WHERE knowledge_point_id='K015'")
        state = self.complete()
        self.assertTrue(state['coverage_limitations'])
        p = next(p for p in state['result']['profile'] if p['knowledge_point_id'] == 'K015')
        self.assertIsNone(p['mastery_score'])

    def test_empty_pool_completes_gracefully(self):
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='draft'")
        state = start_diagnostic('EMPTY')
        self.assertTrue(state['diagnostic_completed'])
        self.assertEqual(state['result']['total'], 0)
        self.assertEqual(len(state['result']['profile']), 15)

    def test_late_unapproval_refuses_write(self):
        state = start_diagnostic('NEW')
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='rejected' WHERE question_id=?", (state['current_question']['id'],))
        with self.assertRaises(ValueError):
            self.submit(state)
        self.assertEqual(self.count_attempts(), 0)

    def test_invalid_answer_time_rolls_back(self):
        state = start_diagnostic('NEW')
        with self.assertRaises(ValueError):
            submit_diagnostic_answer(state['id'], state['current_question']['id'], 'A', answer_time=float('nan'))
        self.assertEqual(self.count_attempts(), 0)

    def test_interrupted_final_report_recovers_without_rewriting_answer(self):
        state = start_diagnostic('RECOVER', max_questions=1)
        with patch('services.diagnostic.generate_recommendation', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.submit(state)
        self.assertEqual(self.count_attempts(), 1)
        restored = restore_diagnostic('RECOVER')
        self.assertTrue(restored['diagnostic_completed'])
        self.assertEqual(restored['result']['total'], 1)
        self.assertEqual(self.count_attempts(), 1)

    def test_invalid_stale_question_does_not_advance_or_write(self):
        state = start_diagnostic('NEW')
        different = next(q for q in state['pool'] if q['id'] != state['current_question']['id'])
        with self.assertRaises(ValueError):
            submit_diagnostic_answer(state['id'], different['id'], 'A')
        self.assertEqual(restore_diagnostic('NEW'), state)
        self.assertEqual(self.count_attempts(), 0)

    def test_completed_snapshot_stays_unchanged_after_later_training(self):
        from database.database import record_attempt
        state = self.complete()
        q = get_training_questions()[0]
        record_attempt('NEW', q['id'], q['answer'], 1, 1.)
        self.assertEqual(restore_diagnostic('NEW'), state)
        self.assertEqual(self.count_attempts(), 19)

    def test_v1_fallback_and_diagnostic_disabled(self):
        with patch.dict(os.environ, {'ACTIVE_TAXONOMY_VERSION': 'function_v1'}):
            self.assertEqual(len(get_training_questions()), 6)
            app = AppTest.from_file(str(ROOT / 'pages/diagnostic.py')).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.info)
            self.assertFalse(app.button)

    def test_real_navigation_pages_and_student_switch(self):
        with patch('services.feedback.generate_text', side_effect=AssertionError('No API')):
            app = AppTest.from_file(str(ROOT / 'app.py')).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, '高中数学个性化学习系统')
            app.text_input[0].set_value('WEB_NEW').run()
            for page in ('diagnostic', 'training', 'profile', 'recommendation', 'feedback'):
                app.switch_page(f'pages/{page}.py').run()
                self.assertFalse(app.exception, page)
            app.switch_page('pages/training.py').run()
            app.button[0].click().run()  # explicitly start personalized adaptive session
            app.radio[0].set_value('A').run()
            next(b for b in app.button if b.label == '提交答案').click().run()
            with closing(get_connection(read_only=True)) as conn:
                self.assertEqual(conn.execute('SELECT student_id FROM attempts').fetchone()[0], 'WEB_NEW')

    def test_page_submit_rerun_refresh_completion_restart_and_targeted_training(self):
        app = AppTest.from_file(str(ROOT / 'app.py')).run().switch_page('pages/diagnostic.py').run()
        app.button[0].click().run()
        for _ in range(18):
            state = app.session_state['diagnostic_state']
            app.radio[0].set_value(state['current_question']['answer']).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
        self.assertTrue(app.session_state['diagnostic_state']['diagnostic_completed'])
        self.assertEqual(self.count_attempts(), 18)
        app.run()
        self.assertEqual(self.count_attempts(), 18)
        self.assertEqual(len(app.dataframe), 4)
        app.button[0].click().run()  # view previous result
        snapshot = app.session_state['diagnostic_state']
        app.button[-1].click().run()  # targeted training via real navigation
        self.assertFalse(app.exception)
        self.assertTrue(app.radio)
        self.assertIn('adaptive_session_id', app.session_state)
        app.switch_page('pages/diagnostic.py').run()
        app.button[1].click().run()  # explicitly restart
        self.assertNotEqual(app.session_state['diagnostic_state']['id'], snapshot['id'])
        fresh = AppTest.from_file(str(ROOT / 'app.py')).run().switch_page('pages/diagnostic.py').run()
        self.assertFalse(fresh.exception)
        self.assertEqual(fresh.session_state['diagnostic_state']['id'], app.session_state['diagnostic_state']['id'])
        self.assertEqual(self.count_attempts(), 18)
