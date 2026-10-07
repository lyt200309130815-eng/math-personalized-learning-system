"""V1.0C integration checks using isolated SQLite databases and real UI."""
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from init_db import initialize_database
from database.database import get_connection, record_attempt, get_approved_questions, get_recent_question_ids
from database.taxonomy_migration import migrate_function_v2
from database.variation import migrate_variation
from scripts.function_v2_dry_run import load_gold
from services.adaptive_training import start_training_session, get_next_question, submit_training_answer, get_training_session, get_training_session_summary, end_training_session
from services.training_support import request_hint, retry_question, select_error_type
from services.question_variation import TEMPLATES, generate_variant, validate_variant, fingerprint, create_runtime_question
from services.mastery import calculate_knowledge_mastery
from database.training_sessions import load_session, save_session


class VariationTrainingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)/'test.db'
        initialize_database(self.path)
        migrate_function_v2(self.path,load_gold())
        env = patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2'})
        env.start()
        self.addCleanup(env.stop)
        migrate_variation()

    def test_templates_reproducible_valid_unique_and_tamper_rejected(self):
        seen = set()
        for name,spec in TEMPLATES.items():
            for seed in range(100):
                q = generate_variant(name,seed=seed)
                self.assertEqual(q,generate_variant(name,seed=seed))
                self.assertTrue(validate_variant(q))
                self.assertEqual(q['variant_fingerprint'],fingerprint(name,dict(reversed(list(q['parameter_set'].items())))))
                bad = copy.deepcopy(q)
                bad['answer'] = next(k for k in 'ABCD' if k != q['answer'])
                self.assertFalse(validate_variant(bad))
                seen.add(q['variant_fingerprint'])
            invalid = {k:0 for k in spec['parameters']}
            invalid[next(iter(invalid))] = 999
            with self.assertRaises(ValueError):
                generate_variant(name,parameters=invalid)
        self.assertGreater(len(seen),100)

    def test_hint_retry_error_evidence_and_existing_mastery(self):
        state = start_training_session('NEW')
        q = get_next_question('NEW',state['id'])
        for level in range(1,5):
            request_hint('NEW',state['id'],level)
        wrong = next(k for k in 'ABCD' if k != q['answer'])
        first = submit_training_answer('NEW',state['id'],q['id'],wrong,10.)
        select_error_type('NEW',state['id'],'C')
        with self.assertRaises(ValueError):
            select_error_type('NEW',state['id'],'X')
        retry_question('NEW',state['id'])
        retry_question('NEW',state['id'])
        submit_training_answer('NEW',state['id'],q['id'],q['answer'],3.)
        submit_training_answer('NEW',state['id'],q['id'],q['answer'],3.)
        with closing(get_connection()) as conn:
            rows = conn.execute('SELECT * FROM attempts ORDER BY id').fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual((rows[0]['user_answer'],rows[0]['error_type'],rows[0]['hint_count'],rows[0]['retry_count']),(wrong,'C',4,0))
            self.assertEqual((rows[1]['is_correct'],rows[1]['retry_count']),(1,1))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM training_hint_events').fetchone()[0],4)
        summary = get_training_session_summary(state['id'])
        self.assertEqual((summary['hint_count'],summary['retry_count'],summary['total']),(4,1,1))
        self.assertEqual(summary['main_error_types'],['C'])
        self.assertEqual(summary['final_mastery'],calculate_knowledge_mastery('NEW','K001')['mastery_score'])
        self.assertNotEqual(get_next_question('NEW',state['id'])['id'],q['id'])

    def test_runtime_generated_training_and_parameter_dedup(self):
        basic = get_approved_questions('K001')[0]
        for _ in range(6):
            record_attempt('NEW',basic['id'],basic['answer'],1,10.)
        for q in get_approved_questions('K002'):
            record_attempt('NEW',q['id'],q['answer'],1,10.)
        state = start_training_session('NEW',target_knowledge_point_id='K002')
        q = get_next_question('NEW',state['id'])
        self.assertEqual(q['source_type'],'generated_template')
        self.assertTrue(validate_variant(q))
        submit_training_answer('NEW',state['id'],q['id'],q['answer'],5.)
        second = get_next_question('NEW',state['id'])
        self.assertNotEqual(q['id'],second['id'])
        with closing(get_connection()) as conn:
            variants = conn.execute('SELECT variant_fingerprint FROM question_variants').fetchall()
            self.assertEqual(len(variants),len({v[0] for v in variants}))
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_migration_idempotent_history_preserved(self):
        with closing(get_connection()) as conn:
            before = list(conn.execute('SELECT * FROM questions'))
        migrate_variation()
        with closing(get_connection()) as conn:
            self.assertEqual([tuple(r) for r in before],[tuple(r) for r in conn.execute('SELECT * FROM questions')])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM question_templates').fetchone()[0],5)

    def test_recent_thirty_distinct_questions_retries_and_oldest_fallback(self):
        with closing(get_connection()) as conn, conn:
            for i in range(35):
                qid = f'WINDOW_{i:02d}'
                conn.execute('INSERT INTO questions SELECT ?,stem,options,answer,explanation,knowledge_point_id,1,ability_tag,question_type,estimated_time FROM questions WHERE id=\'Q001\'',(qid,))
                conn.execute("INSERT INTO question_knowledge_mappings VALUES ('function_v2',?,'K001','primary','approved')",(qid,))
                conn.execute('INSERT INTO attempts(student_id,question_id,user_answer,is_correct,answer_time) VALUES (?,?,\'A\',1,10)',('NEW',qid))
        for _ in range(12):
            record_attempt('NEW','WINDOW_34','A',1,10.)
        recent = get_recent_question_ids('NEW')
        self.assertEqual(len(recent),30)
        self.assertNotIn('WINDOW_04',recent)
        self.assertIn('WINDOW_05',recent)
        state = start_training_session('NEW',target_knowledge_point_id='K001')
        q = get_next_question('NEW',state['id'])
        self.assertNotIn(q['id'],recent)
        end_training_session('NEW',state['id'])
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='rejected' WHERE knowledge_point_id='K001' AND question_id NOT IN ('WINDOW_05','WINDOW_34')")
        state = start_training_session('NEW',target_knowledge_point_id='K001')
        self.assertEqual(get_next_question('NEW',state['id'])['id'],'WINDOW_05')

    def test_fresh_difficulty_relaxed_before_recent_question(self):
        q = get_approved_questions('K001')[0]
        for _ in range(12):
            record_attempt('NEW',q['id'],q['answer'],1,10.)
        with closing(get_connection()) as conn, conn:
            conn.execute("UPDATE question_knowledge_mappings SET review_status='rejected' WHERE knowledge_point_id='K001' AND question_id!=?",(q['id'],))
            conn.execute('INSERT INTO questions SELECT \'FRESH_D4\',stem,options,answer,explanation,knowledge_point_id,4,ability_tag,question_type,estimated_time FROM questions WHERE id=?',(q['id'],))
            conn.execute("INSERT INTO question_knowledge_mappings VALUES ('function_v2','FRESH_D4','K001','primary','approved')")
        state = start_training_session('NEW',target_knowledge_point_id='K001')
        with closing(get_connection()) as conn, conn:
            state['difficulty'] = 1
            save_session(conn,state)
        self.assertEqual(get_next_question('NEW',state['id'])['id'],'FRESH_D4')

    def test_generated_metadata_reload_validator_and_approval(self):
        state = start_training_session('NEW')
        state['target_knowledge_point_id'] = 'K002'
        with closing(get_connection()) as conn, conn:
            q = create_runtime_question(conn,state)
        reloaded = next(v for v in get_approved_questions('K002') if v['id']==q['id'])
        self.assertTrue(validate_variant(reloaded))
        self.assertEqual(q['hints'],reloaded['hints'])
        self.assertEqual(reloaded['generator_version'],'1')

    def test_web_hints_error_retry_and_summary(self):
        root = Path(__file__).resolve().parents[1]
        with patch('services.feedback.generate_text',side_effect=AssertionError('LLM must not decide')):
            app = AppTest.from_file(str(root/'app.py')).run().switch_page('pages/training.py').run()
            next(b for b in app.button if b.label=='开始个性化训练').click().run()
            for label in ('提示1','提示2','提示3','查看完整解析'):
                next(b for b in app.button if b.label==label).click().run()
                self.assertFalse(app.exception)
            state = app.session_state['adaptive_training_state']
            q = state['current_question']
            app.radio[0].set_value(next(k for k in 'ABCD' if k != q['answer'])).run()
            next(b for b in app.button if b.label=='提交答案').click().run()
            next(s for s in app.selectbox if s.label=='你觉得自己主要卡在哪里？').set_value('C').run()
            next(b for b in app.button if b.label=='保存错因').click().run()
            next(b for b in app.button if b.label=='再试一次').click().run()
            app.radio[0].set_value(q['answer']).run()
            next(b for b in app.button if b.label=='提交答案').click().run()
            next(b for b in app.button if b.label=='结束本轮训练').click().run()
            self.assertFalse(app.exception)
            summary = get_training_session_summary(state['id'])
            self.assertEqual((summary['hint_count'],summary['retry_count'],summary['main_error_types']),(4,1,['C']))
