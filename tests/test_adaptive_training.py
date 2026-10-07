"""Adaptive decisions, atomic sessions and the actual Streamlit learning loop."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.database import get_connection, get_approved_questions, record_attempt
from database.taxonomy_migration import migrate_function_v2, protected_snapshot
from database.training_sessions import migrate_training_sessions, get_attempt_mode
from init_db import initialize_database
from scripts.function_v2_dry_run import load_gold
from services.adaptive_training import (
    start_training_session, get_next_question, submit_training_answer, get_training_session,
    get_training_session_summary, end_training_session, initial_difficulty,
)
from services.mastery import calculate_knowledge_mastery
from services.recommendation import generate_recommendation

ROOT = Path(__file__).resolve().parents[1]


class AdaptiveTrainingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'adaptive.db'
        initialize_database(self.path)
        migrate_function_v2(self.path, load_gold())
        env = patch.dict(os.environ, {'MATH_AI_DATABASE_PATH': str(self.path), 'ACTIVE_TAXONOMY_VERSION': 'function_v2',
            'OPENAI_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'GEMINI_API_KEY': ''})
        env.start()
        self.addCleanup(env.stop)

    def seed(self, key, student='NEW', count=6, correct=True):
        q = get_approved_questions(key)[0]
        for _ in range(count):
            choice = q['answer'] if correct else next(k for k in 'ABCD' if k != q['answer'])
            record_attempt(student, q['id'], choice, int(correct), 1.)

    def ready(self, student='NEW'):
        for key in ('K001', 'K002', 'K007', 'K008', 'K009', 'K010'):
            self.seed(key, student)

    def answer(self, state, correct=True):
        q = get_next_question(state['student_id'], state['id'])
        if q is None:
            return get_training_session(state['student_id'], state['id'])
        answer = q['answer'] if correct else next(k for k in 'ABCD' if k != q['answer'])
        return submit_training_answer(state['student_id'], state['id'], q['id'], answer, 2.)

    def count(self):
        with closing(get_connection(read_only=True)) as conn:
            return conn.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]

    def test_new_student_starts_from_recommendation_and_basic_difficulty(self):
        recommendation = generate_recommendation('NEW')
        state = start_training_session('NEW')
        self.assertEqual(state['target_knowledge_point_id'], recommendation['target_knowledge']['knowledge_point_id'])
        self.assertIsNone(state['initial_mastery'])
        self.assertEqual(state['difficulty'], 1)
        self.assertIn(get_next_question('NEW', state['id'])['difficulty'], (1, 2))
        self.assertEqual(self.count(), 0)

    def test_initial_difficulty_thresholds(self):
        for score, expected in ((None, 1), (.39, 1), (.4, 2), (.59, 2), (.6, 2), (.79, 2), (.8, 3), (.89, 3), (.9, 4), (1., 4)):
            self.assertEqual(initial_difficulty({'mastery_score': score}), expected)

    def test_two_correct_raise_cautiously_and_update_mastery(self):
        state = start_training_session('NEW')
        state = self.answer(state)
        self.assertEqual(state['difficulty'], 1)
        state = self.answer(state)
        self.assertEqual(state['difficulty'], 2)
        self.assertEqual(state['mastery']['attempt_count'], 2)
        self.assertEqual(state['final_mastery'], calculate_knowledge_mastery('NEW', 'K001')['mastery_score'])
        self.assertLessEqual(state['difficulty'], 2)

    def test_low_mastery_cannot_jump_to_d5_after_two_lucky_answers(self):
        self.seed('K001', count=12, correct=False)
        state = start_training_session('NEW', target_knowledge_point_id='K001')
        state = self.answer(self.answer(state))
        self.assertLess(state['final_mastery'], .4)
        self.assertLessEqual(state['difficulty'], 2)

    def test_two_errors_lower_difficulty_and_bounds(self):
        self.ready()
        self.seed('K003')
        state = start_training_session('NEW', target_knowledge_point_id='K003')
        self.assertEqual(state['difficulty'], 4)
        state = self.answer(self.answer(state, False), False)
        self.assertLess(state['difficulty'], 4)
        self.assertTrue(1 <= state['difficulty'] <= 5)

    def test_user_selected_target_resolves_only_required_prerequisites(self):
        state = start_training_session('NEW', target_knowledge_point_id='K014')
        self.assertEqual(state['target_knowledge_point_id'], 'K001')
        end_training_session('NEW', state['id'])
        for key in ('K001','K002','K003','K004'):
            self.seed(key)
        state = start_training_session('NEW', target_knowledge_point_id='K014')
        self.assertEqual(state['target_knowledge_point_id'], 'K013')

    def test_related_knowledge_is_not_required_but_question_prerequisite_is(self):
        for key in ('K001', 'K002', 'K008', 'K009'):
            self.seed(key)
        state = start_training_session('NEW', target_knowledge_point_id='K003')
        q = get_next_question('NEW', state['id'])
        self.assertEqual(q['knowledge_point_id'], 'K003')
        self.assertNotEqual(q['id'], 'Q005')  # Q005 explicitly requires K007
        self.assertIsNone(calculate_knowledge_mastery('NEW','K007')['mastery_score'])

    def test_external_prerequisite_weakness_stops_session_with_real_fallback(self):
        self.ready()
        state = start_training_session('NEW', target_knowledge_point_id='K003')
        get_next_question('NEW', state['id'])
        self.seed('K002', count=24, correct=False)
        self.assertIsNone(get_next_question('NEW', state['id']))
        state = get_training_session('NEW', state['id'])
        self.assertEqual(state['status'], 'prerequisite_blocked')
        self.assertEqual(state['next_target']['knowledge_point_id'], 'K002')

    def test_recent_question_avoided_and_session_never_repeats(self):
        q = get_approved_questions('K001')[0]
        record_attempt('NEW', q['id'], q['answer'], 1, 2.)
        state = start_training_session('NEW', target_knowledge_point_id='K001')
        chosen = get_next_question('NEW', state['id'])
        self.assertNotEqual(chosen['id'], q['id'])
        while state['status'] == 'active':
            state = self.answer(state)
        ids = [a['question_id'] for a in state['answers']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_new_history_uses_recent_but_never_reuses_in_session(self):
        for q in get_approved_questions('K001'):
            record_attempt('NEW', q['id'], 'A', 0, 1.)
        state = start_training_session('NEW', target_knowledge_point_id='K001')
        self.assertIsNotNone(get_next_question('NEW', state['id']))
        state = get_training_session('NEW', state['id'])
        self.assertIn('近期可用新题不足', state['selection_note'])

    def test_all_unapproved_statuses_are_excluded(self):
        for status in ('reviewed','draft','rejected'):
            with self.subTest(status=status):
                with closing(get_connection()) as conn, conn:
                    conn.execute("UPDATE question_knowledge_mappings SET review_status=? WHERE taxonomy_version='function_v2' AND knowledge_point_id='K001'", (status,))
                state = start_training_session('NEW', target_knowledge_point_id='K001')
                self.assertIsNone(get_next_question('NEW', state['id']))
                self.assertEqual(get_training_session('NEW',state['id'])['status'], 'coverage_limited')

    def test_late_unapproved_question_cannot_be_submitted(self):
        state = start_training_session('NEW')
        q = get_next_question('NEW', state['id'])
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='rejected' WHERE question_id=?", (q['id'],))
        with self.assertRaises(ValueError):
            submit_training_answer('NEW', state['id'], q['id'], q['answer'], 1.)
        self.assertEqual(self.count(), 0)
        replacement = get_next_question('NEW',state['id'])
        self.assertNotEqual(replacement['id'],q['id'])

    def test_five_correct_can_complete_without_changing_target(self):
        self.ready()
        state = start_training_session('NEW', target_knowledge_point_id='K003')
        for _ in range(5):
            state = self.answer(state)
        self.assertEqual(state['status'],'completed')
        self.assertEqual(len(state['answers']),5)
        self.assertEqual(state['target_knowledge_point_id'],'K003')
        summary = get_training_session_summary(state['id'])
        self.assertEqual(summary['correct'],5)
        self.assertEqual(summary['final_mastery'],1.)
        self.assertGreater(max(summary['actual_difficulties']), min(summary['actual_difficulties']))

    def test_eight_question_limit_with_mixed_results(self):
        # Synthetic rows only in this disposable test database, not the real bank.
        with closing(get_connection()) as conn, conn:
            for i in range(12):
                qid = f'TEST_ADAPTIVE_{i:02d}'
                conn.execute('''INSERT INTO questions SELECT ?,stem,options,answer,explanation,knowledge_point_id,
                    1,ability_tag,question_type,estimated_time FROM questions WHERE id='Q001' ''', (qid,))
                conn.execute("INSERT INTO question_knowledge_mappings VALUES ('function_v2',?,'K001','primary','approved')", (qid,))
        self.seed('K001', count=10, correct=False)
        state = start_training_session('NEW',target_knowledge_point_id='K001')
        for i in range(8):
            state = self.answer(state, i % 2 == 0)
        self.assertEqual(state['status'],'completed')
        self.assertEqual(len(state['answers']),8)

    def test_three_clear_failures_stop_with_support_and_not_fake_related_fallback(self):
        state = start_training_session('NEW')
        for _ in range(3):
            state = self.answer(state,False)
        self.assertEqual(state['status'],'needs_support')
        self.assertEqual(state['target_knowledge_point_id'],'K001')
        self.assertIsNone(state['next_target'])

    def test_user_can_end_early_and_resume_does_not_create_duplicate_session(self):
        state = start_training_session('NEW')
        self.assertEqual(start_training_session('NEW')['id'],state['id'])
        state = self.answer(state)
        end_training_session('NEW',state['id'])
        summary = get_training_session_summary(state['id'])
        self.assertEqual(summary['total'],1)
        self.assertEqual(summary['status'],'user_ended')
        self.assertNotEqual(start_training_session('NEW')['id'],state['id'])

    def test_sparse_bank_finishes_gracefully(self):
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='draft' WHERE knowledge_point_id='K001' AND question_id!='Q001'")
        state = self.answer(start_training_session('NEW',target_knowledge_point_id='K001'))
        self.assertIsNone(get_next_question('NEW',state['id']))
        self.assertEqual(get_training_session('NEW',state['id'])['status'],'coverage_limited')

    def test_difficulty_gaps_do_not_force_unsafe_hard_question(self):
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE questions SET difficulty=5 WHERE id IN (SELECT question_id FROM question_knowledge_mappings WHERE taxonomy_version='function_v2' AND knowledge_point_id='K001')")
        state = start_training_session('NEW',target_knowledge_point_id='K001')
        self.assertIsNone(get_next_question('NEW',state['id']))
        self.assertEqual(self.count(),0)

    def test_atomic_failure_rolls_back_attempt_and_session_changes(self):
        state = start_training_session('NEW')
        q = get_next_question('NEW',state['id'])
        before = get_training_session('NEW',state['id'])
        with patch('services.adaptive_training.calculate_knowledge_mastery',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                submit_training_answer('NEW',state['id'],q['id'],q['answer'],1.)
        self.assertEqual(self.count(),0)
        self.assertEqual(get_training_session('NEW',state['id']),before)

    def test_concurrent_duplicate_submissions_are_exactly_once(self):
        state = start_training_session('NEW')
        q = get_next_question('NEW',state['id'])
        def send(_):
            return submit_training_answer('NEW',state['id'],q['id'],q['answer'],1.)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(send,range(2)))
        self.assertEqual(replies[0]['answers'],replies[1]['answers'])
        self.assertEqual(self.count(),1)

    def test_question_retrieval_is_idempotent_and_checks_student_ownership(self):
        state = start_training_session('NEW')
        a = get_next_question('NEW',state['id'])
        before = get_training_session('NEW',state['id'])
        self.assertEqual(get_next_question('NEW',state['id']),a)
        self.assertEqual(get_training_session('NEW',state['id']),before)
        with self.assertRaises(ValueError):
            get_next_question('OTHER',state['id'])
        with self.assertRaises(ValueError):
            submit_training_answer('OTHER',state['id'],a['id'],'A',1.)

    def test_migration_idempotent_and_historical_attempt_modes(self):
        self.seed('K001',count=1)
        with closing(get_connection(read_only=True)) as conn:
            before = protected_snapshot(conn)
        self.assertTrue(migrate_training_sessions()['applied'])
        self.assertFalse(migrate_training_sessions()['applied'])
        with closing(get_connection(read_only=True)) as conn:
            self.assertEqual(protected_snapshot(conn),before)
        self.assertEqual(get_attempt_mode(1),'legacy')
        state = self.answer(start_training_session('NEW'))
        self.assertEqual(get_attempt_mode(state['answers'][0]['attempt_id']),'training')

    def test_migration_failure_rolls_back_partial_schema(self):
        import sqlite3
        from database.training_sessions import SCHEMA
        with closing(get_connection(read_only=True)) as conn:
            before = protected_snapshot(conn)
        with patch('database.training_sessions.SCHEMA', SCHEMA + ('THIS IS NOT VALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):
                migrate_training_sessions()
        with closing(get_connection(read_only=True)) as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='training_sessions'").fetchone())
            self.assertEqual(protected_snapshot(conn), before)

    def test_invalid_input_and_stale_question_do_not_write(self):
        state = start_training_session('NEW')
        q = get_next_question('NEW',state['id'])
        for answer, duration in (('X',1.),('A',-1.),('A',float('nan'))):
            with self.assertRaises(ValueError):
                submit_training_answer('NEW',state['id'],q['id'],answer,duration)
        with self.assertRaises(ValueError):
            submit_training_answer('NEW',state['id'],'Q002','A',1.)
        self.assertEqual(self.count(),0)

    def test_recommendation_is_target_authority(self):
        self.ready()
        recommended = generate_recommendation('NEW')['target_knowledge']
        with patch('services.adaptive_training.generate_recommendation',return_value={'target_knowledge':recommended}) as service:
            state = start_training_session('NEW')
        service.assert_called_once()
        self.assertEqual(state['target_knowledge_point_id'],recommended['knowledge_point_id'])

    def test_web_diagnostic_profile_five_adaptive_questions_recommendation_and_feedback(self):
        with patch('services.feedback.generate_text',side_effect=AssertionError('No LLM for learning decisions')):
            app = AppTest.from_file(str(ROOT/'app.py')).run().switch_page('pages/diagnostic.py').run()
            app.button[0].click().run()
            for _ in range(18):
                q = app.session_state['diagnostic_state']['current_question']
                answer = next(k for k in 'ABCD' if k != q['answer']) if q['knowledge_point_id']=='K003' else q['answer']
                app.radio[0].set_value(answer).run()
                app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(get_attempt_mode(1),'diagnostic')
            diagnostic = app.session_state['diagnostic_state']
            app.switch_page('pages/profile.py').run()
            self.assertFalse(app.exception)
            app.switch_page('pages/diagnostic.py').run()
            next(b for b in app.button if b.label=='开始针对性训练').click().run()
            self.assertFalse(app.exception)
            # Follow the frontend page redirect in AppTest before more interactions.
            app.switch_page('pages/training.py').run()
            self.assertEqual(app.session_state['adaptive_training_state']['target_knowledge_point_id'],'K003')
            for i in range(5):
                state = app.session_state['adaptive_training_state']
                q = state['current_question']
                app.radio[0].set_value(q['answer']).run()
                next(b for b in app.button if b.label=='提交答案').click().run()
                self.assertFalse(app.exception)
                count = self.count()
                app.run()
                self.assertEqual(self.count(),count)
                if i < 4:
                    next(b for b in app.button if b.label=='下一题').click().run()
            state = app.session_state['adaptive_training_state']
            self.assertEqual(state['status'],'completed')
            self.assertGreater(state['final_mastery'],state['initial_mastery'])
            self.assertGreater(max(a['difficulty'] for a in state['answers']),min(a['difficulty'] for a in state['answers']))
            self.assertNotEqual(generate_recommendation('S001')['target_knowledge']['knowledge_point_id'],
                                diagnostic['result']['recommendation']['target_knowledge']['knowledge_point_id'])
            app.switch_page('pages/feedback.py').run()
            next(b for b in app.button if b.label=='查看规则式学习反馈').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state['learning_feedback'])

    def test_browser_refresh_restores_submitted_question_without_writing(self):
        app = AppTest.from_file(str(ROOT/'app.py')).run().switch_page('pages/training.py').run()
        next(b for b in app.button if b.label=='开始个性化训练').click().run()
        q = app.session_state['adaptive_training_state']['current_question']
        app.radio[0].set_value(q['answer']).run()
        next(b for b in app.button if b.label=='提交答案').click().run()
        fresh = AppTest.from_file(str(ROOT/'app.py')).run().switch_page('pages/training.py').run()
        self.assertFalse(fresh.exception)
        self.assertTrue(fresh.session_state['adaptive_training_state']['submitted'])
        self.assertEqual(fresh.session_state['adaptive_training_state']['current_question']['id'],q['id'])
        self.assertEqual(self.count(),1)

    def test_v1_fallback_remains_legacy_training(self):
        with patch.dict(os.environ, {'ACTIVE_TAXONOMY_VERSION':'function_v1'}):
            app = AppTest.from_file(str(ROOT/'app.py')).run().switch_page('pages/training.py').run()
            self.assertTrue(app.radio)
            app.radio[0].set_value('D').run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state['submitted'])
