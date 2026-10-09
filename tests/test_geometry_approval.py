"""Production recovery approval contracts; all mutations use disposable databases."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import os
from streamlit.testing.v1 import AppTest

from database.database import get_connection,get_approved_questions,record_attempt
from database.geometry import import_geometry
from database.taxonomy_migration import protected_snapshot
from services.geometry_production_approval import (BATCH,NOTES,UNRECOVERABLE,prepare_approval,
    production_gate,duplicate_audit,integrate,load_geometry_rows,baseline)
from services.geometry_review import ROOT,read_rows
from services.geometry_quality import source_fingerprint
from services.question_validator import content_fingerprint
from services.question_assets import visible_assets,geometry_trainable
from services.question_renderer import render_question,render_solution
from services.question_type_policy import question_type_ratios
from services.adaptive_training import start_training_session,get_next_question,exposure_tokens,submit_training_answer
from services.diagnostic import generate_diagnostic_test
from geometry_baseline import historical_database


class RecoveryApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=read_rows(BATCH)
        with closing(get_connection(historical_database(),read_only=True)) as conn:
            cls.existing=load_geometry_rows(conn)
        cls.approved,cls.audit=prepare_approval(cls.rows,cls.existing)

    def test_manual_approval_preserves_review_and_content(self):
        self.assertEqual(len(self.approved),113)
        for old,q in zip(self.rows,self.approved):
            self.assertEqual(q['review_status'],'approved')
            self.assertEqual(q['reviewed_by'],'manual_user')
            self.assertEqual(q['review_notes'],NOTES)
            self.assertEqual(content_fingerprint(old),content_fingerprint(q))

    def test_production_gate_every_recovery_question(self):
        self.assertTrue(all(q['trainable'] for q in self.approved))
        for q in self.approved:self.assertEqual(production_gate(q),[],q['id'])

    def test_approved_but_blocked_remains_manually_approved(self):
        q=deepcopy(self.rows[0]);q['difficulty']=6
        prepared,_=prepare_approval([q],self.existing)
        self.assertEqual(prepared[0]['review_status'],'approved')
        self.assertEqual(prepared[0]['decision'],'approved_but_blocked')
        self.assertFalse(prepared[0]['trainable'])

    def test_blocked_gate_cannot_enter_runtime_pool(self):
        q=dict(self.approved[0],production_gate_status='blocked')
        self.assertFalse(geometry_trainable(q,check_files=False))

    def test_invalid_answer_structure_blocked(self):
        q=deepcopy(next(q for q in self.approved if q['question_type']=='multiple_choice'))
        q['correct_answers']=['A','A'];q['fingerprint']=content_fingerprint(q)
        self.assertIn('invalid_multiple_answer_set',production_gate(q))

    def test_raw_formula_not_trusted_despite_valid_status(self):
        q=deepcopy(self.approved[0]);q['stem']+=' [公式待核]';q['fingerprint']=content_fingerprint(q)
        self.assertIn('raw_or_unresolved_formula',production_gate(q))

    def test_missing_asset_is_blocked(self):
        q=deepcopy(next(q for q in self.approved if q['diagram_required']))
        q['diagram_assets']=[]
        self.assertIn('missing_required_question_diagram',production_gate(q))

    def test_unknown_primary_is_blocked(self):
        q=dict(self.approved[0],primary_knowledge_point_id='G999')
        self.assertIn('primary_not_in_catalog',production_gate(q))

    def test_unrecoverable_special_font_excluded(self):
        self.assertNotIn(UNRECOVERABLE,{q['id'] for q in self.approved})
        with self.assertRaises(ValueError):prepare_approval([dict(self.rows[0],id=UNRECOVERABLE)],[])

    def test_five_duplicate_checks_and_batch_duplicates(self):
        q=self.approved[0]
        audit=duplicate_audit([q],[q])[0]
        self.assertEqual(set(audit['duplicates']),{'question_id','exact_text','normalized_text','source_fingerprint','variant_fingerprint'})
        self.assertFalse(audit['already_integrated'])
        self.assertTrue(duplicate_audit([q],[q],allow_identical=True)[0]['already_integrated'])
        self.assertTrue(duplicate_audit([q,dict(q,id='OTHER')],[])[1]['duplicates'])

    def test_normalized_text_duplicate_despite_spacing_and_answer_changes(self):
        q=self.approved[0];other=dict(q,id='OTHER',stem='  '+q['stem']+'\n ',answer='B')
        self.assertIn('normalized_text',duplicate_audit([other],[q])[0]['duplicates'])

    def test_different_problem_same_knowledge_allowed(self):
        self.assertFalse(any(a['duplicates'] for a in self.audit))

    def test_g008_coverage_has_seven_genuine_recoveries(self):
        self.assertEqual(sum(q['primary_knowledge_point_id']=='G008' for q in self.approved),7)

    def test_recovery_difficulty_distribution(self):
        from collections import Counter
        self.assertEqual(Counter(q['difficulty'] for q in self.approved),{1:4,2:22,3:60,4:23,5:4})

    def test_high_mastery_subjective_weighting(self):
        self.assertGreater(question_type_ratios(.95)['subjective'],question_type_ratios(.2)['subjective'])
        self.assertGreater(question_type_ratios(.65)['fill_blank'],question_type_ratios(.2)['fill_blank'])

    def test_question_diagram_visible(self):
        q=next(q for q in self.approved if visible_assets(q))
        st=MagicMock()
        with patch('services.question_renderer.render_math_text'),patch('services.question_renderer.readable_asset',return_value=True),patch('services.question_assets.readable_asset',return_value=True):
            self.assertTrue(render_question(st,q));self.assertEqual(st.image.call_count,len(visible_assets(q)))

    def test_solution_diagram_isolated(self):
        q=next(q for q in self.approved if visible_assets(q,solution=True));st=MagicMock()
        render_solution(st,q,submitted=False);st.image.assert_not_called()
        with patch('services.question_renderer.render_math_text'),patch('services.question_renderer.readable_asset',return_value=True):
            render_solution(st,q,submitted=True)
        self.assertEqual(st.image.call_count,len(visible_assets(q,solution=True)))


class RecoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)/'integration.db'
        with closing(get_connection(historical_database(),read_only=True)) as src,closing(get_connection(cls.path)) as dst:src.backup(dst)
        cls.function=get_approved_questions(database_path=cls.path,taxonomy_version='function_v2')
        cls.result=integrate(cls.path,output=Path(cls.temp.name)/'audit')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def clone(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);path=Path(folder.name)/'test.db'
        with closing(get_connection(self.path,read_only=True)) as src,closing(get_connection(path)) as dst:src.backup(dst)
        return path

    def test_manual_approval_lands_in_database(self):
        with closing(get_connection(self.path,read_only=True)) as conn:
            rows=conn.execute('SELECT * FROM geometry_recovery_reviews').fetchall()
        self.assertEqual(len(rows),113)
        self.assertTrue(all(r['review_status']=='approved' and r['reviewed_by']=='manual_user' and r['review_notes']==NOTES for r in rows))

    def test_migration_idempotency(self):
        result=integrate(self.path,output=Path(self.temp.name)/'rerun')
        self.assertEqual(result['inserted'],0);self.assertEqual(result['skipped'],113)

    def test_attempts_count_digest_unchanged(self):
        self.assertEqual(self.result['baseline_before']['attempts_count'],self.result['baseline_after']['attempts_count'])
        self.assertEqual(self.result['baseline_before']['attempts_digest'],self.result['baseline_after']['attempts_digest'])

    def test_backup_integrity_and_sha256(self):
        self.assertEqual(self.result['backup_integrity_check'],'ok')
        self.assertEqual(len(self.result['backup_sha256']),64)

    def test_function_v2_isolation(self):
        self.assertEqual(self.function,get_approved_questions(database_path=self.path,taxonomy_version='function_v2'))
        state=generate_diagnostic_test('TEST_FUNCTION_V11E','function_v2',database_path=self.clone())
        self.assertTrue(all(q['knowledge_point_id'].startswith('K') for q in state['pool']))

    def test_trainable_pool_coverage(self):
        pool=get_approved_questions(database_path=self.path,taxonomy_version='geometry_v1')
        self.assertEqual(len(pool),236);self.assertEqual(sum(q['knowledge_point_id']=='G008' for q in pool),8)
        self.assertNotIn(UNRECOVERABLE,{q['id'] for q in pool})

    def test_diagnostic_mix_and_coverage(self):
        state=generate_diagnostic_test('TEST_GEO_V11E','geometry_v1',database_path=self.clone())
        qs=[q for q in state['pool'] if q['id'] in state['planned_question_ids']]
        self.assertEqual(len(qs),15);self.assertEqual(len({q['knowledge_point_id'] for q in qs}),10)
        self.assertEqual(len({q['question_type'] for q in qs}),4)
        self.assertLess(sum(q['question_type'] in ('single_choice','multiple_choice') for q in qs),8)

    def test_real_pool_adaptive_d4_and_d5_selection(self):
        path=self.clone();student='TEST_STABLE';score=dict(mastery_score=.95,attempt_count=8,source_evidence_count=8)
        with patch('services.adaptive_training.calculate_knowledge_mastery',return_value=score):
            state=start_training_session(student,'geometry_v1',target_knowledge_point_id='G001',database_path=path)
            q=get_next_question(student,state['id'],database_path=path)
        self.assertIn(q['difficulty'],(4,5))
        # G007 actually contains D5: select the real pool without fabricating questions.
        pool=get_approved_questions('G007',database_path=path,taxonomy_version='geometry_v1')
        with patch('services.adaptive_training.calculate_knowledge_mastery',return_value=score),patch('services.adaptive_training._eligible',return_value=pool),patch('services.adaptive_training._target',return_value={'knowledge_point_id':'G007'}):
            with closing(get_connection(path)) as conn,conn:
                from database.training_sessions import load_session,save_session
                state=load_session(conn,state['id'],student);state.update(current_question=None,target_knowledge_point_id='G007',difficulty=5);save_session(conn,state)
            q=get_next_question(student,state['id'],database_path=path)
        self.assertEqual(q['difficulty'],5)

    def test_low_mastery_avoids_difficult_subjective(self):
        path=self.clone();student='TEST_LOW'
        state=start_training_session(student,'geometry_v1',target_knowledge_point_id='G001',database_path=path)
        q=get_next_question(student,state['id'],database_path=path)
        self.assertLessEqual(q['difficulty'],2);self.assertNotEqual(q['question_type'],'subjective')

    def test_recent_exposure_and_source_fingerprint_avoidance(self):
        path=self.clone();student='TEST_RECENT'
        state=generate_diagnostic_test(student,'geometry_v1',database_path=path)
        qs=[q for q in state['pool'] if q['id'] in state['planned_question_ids'] and q['knowledge_point_id']=='G001']
        for q in qs:record_attempt(student,q['id'],'A' if q['question_type']=='single_choice' else 'wrong',0,1,database_path=path,taxonomy_version='geometry_v1')
        state=start_training_session(student,'geometry_v1',target_knowledge_point_id='G001',database_path=path)
        chosen=get_next_question(student,state['id'],database_path=path)
        self.assertIsNotNone(chosen)
        self.assertTrue(all(not exposure_tokens(chosen)&exposure_tokens(q) for q in qs))

    def test_transaction_failure_rolls_back_review_and_questions(self):
        path=self.clone()
        with closing(get_connection(path,read_only=True)) as conn:before=protected_snapshot(conn)
        with patch('database.geometry.store_status',side_effect=RuntimeError('simulated write failure')):
            q=deepcopy(read_rows(BATCH)[0]);q.update(id='TEST_ROLLBACK',stem=q['stem']+'（回滚测试）',quality_status='approved',review_status='approved',warnings=[])
            q['fingerprint']=content_fingerprint(q)
            with self.assertRaises(RuntimeError):import_geometry(path,[q])
        with closing(get_connection(path,read_only=True)) as conn:self.assertEqual(protected_snapshot(conn),before)

    def test_baseline_change_refuses_import_without_losing_attempts(self):
        path=self.clone();_,snap=baseline(path)
        q=self.function[0];record_attempt('TEST_CONCURRENT',q['id'],'A',0,1,database_path=path,taxonomy_version='function_v2')
        with self.assertRaises(ValueError):import_geometry(path,[],expected_baseline=snap)
        with closing(get_connection(path,read_only=True)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM attempts WHERE student_id='TEST_CONCURRENT'").fetchone()[0],1)

    def test_blocked_approval_persisted_without_import(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        path=Path(folder.name)/'blocked.db'
        with closing(get_connection(historical_database(),read_only=True)) as src,closing(get_connection(path)) as dst:src.backup(dst)
        rows=deepcopy(read_rows(BATCH));rows[0]['difficulty']=6
        with patch('services.geometry_production_approval.read_rows',return_value=rows):
            result=integrate(path,output=Path(folder.name)/'audit')
        self.assertEqual(result['inserted'],112);self.assertEqual(len(result['blocked']),1)
        with closing(get_connection(path,read_only=True)) as conn:
            self.assertFalse(conn.execute('SELECT 1 FROM questions WHERE id=?',(rows[0]['id'],)).fetchone())
            review=conn.execute('SELECT review_status,gate_status FROM geometry_recovery_reviews WHERE question_id=?',(rows[0]['id'],)).fetchone()
        self.assertEqual(tuple(review),('approved','blocked'))

    def test_student_ui_context_survives_reruns_and_pages(self):
        path=self.clone()
        with patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(path),'ACTIVE_TAXONOMY_VERSION':'function_v2'}):
            app=AppTest.from_file(str(ROOT/'app.py')).run()
            app.text_input[0].set_value('TEST_GEO_V11E_UI').run()
            app.run().switch_page('pages/profile.py').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['student_id'],'TEST_GEO_V11E_UI')

    def test_topic_ui_context_survives_switching_both_ways(self):
        path=self.clone()
        with patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(path),'ACTIVE_TAXONOMY_VERSION':'function_v2'}):
            app=AppTest.from_file(str(ROOT/'app.py')).run()
            app.selectbox[0].select('geometry_v1').run().run()
            self.assertEqual(app.session_state['active_taxonomy_version'],'geometry_v1')
            app.switch_page('pages/profile.py').run()
            self.assertTrue(any('当前专题：立体几何与空间向量' in t.value for t in app.markdown))
            app.selectbox[0].select('function_v2').run().run()
            self.assertEqual(app.session_state['active_taxonomy_version'],'function_v2')
            self.assertFalse(app.exception)
