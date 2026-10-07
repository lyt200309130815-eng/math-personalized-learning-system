"""Production integration behavior on disposable SQLite databases only."""
from contextlib import closing
from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock

from PIL import Image
from streamlit.testing.v1 import AppTest
from init_db import initialize_database
from database.database import get_connection,get_approved_questions,record_attempt,get_training_questions
from database.taxonomy_migration import migrate_function_v2
from database.training_review import migrate_training_review,pending_counts
from database.training_sessions import save_session
from services.question_importer import activate_training_questions
from services.adaptive_training import start_training_session,get_next_question,submit_training_answer,get_training_session_summary,end_training_session,exposure_tokens
from services.answer_evaluator import evaluate_question,evaluate_fill_blank,evaluate_answer_result
from services.mastery import calculate_knowledge_mastery
from services.profile import build_profile_data
from services.feedback import build_feedback_context
from services.question_renderer import render_question,render_feedback
from services.question_type_policy import question_type_ratios,select_question_type
from scripts.function_v2_dry_run import load_gold
from scripts.integrate_multitype_production import integrate,load_approved
from scripts.approve_multitype_batches import NOTE
from test_multitype_expansion import multi,subjective
from test_multi_type import typed_fixture
import test_multi_type

ROOT=Path(__file__).resolve().parents[1]


class ProductionTrainingTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'production_test.db'
        initialize_database(self.path);migrate_function_v2(self.path,load_gold())
        env=patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2'})
        env.start();self.addCleanup(env.stop)
        migrate_training_review(self.path)
        activate_training_questions([multi(),typed_fixture(),subjective()],database_path=self.path)

    force_question=test_multi_type.MultiTypeIntegrationTests.force_question

    def test_multiple_exact_correct(self):self.assertTrue(evaluate_question(multi(),['A','B']))
    def test_multiple_order(self):self.assertTrue(evaluate_question(multi(),['B','A']))
    def test_multiple_missing(self):self.assertFalse(evaluate_question(multi(),['A']))
    def test_multiple_extra(self):self.assertFalse(evaluate_question(multi(),['A','B','C']))
    def test_numeric(self):self.assertTrue(evaluate_fill_blank('0.5','1/2','numeric'))
    def test_expression(self):self.assertTrue(evaluate_fill_blank('(x-1)(x+1)','x^2-1','expression'))
    def test_interval_normalization(self):self.assertTrue(evaluate_fill_blank('（-∞，2）','(-inf,2)','interval'))
    def test_set(self):self.assertTrue(evaluate_fill_blank('{0.5,2}','{2,1/2}','set'))
    def test_text(self):self.assertTrue(evaluate_fill_blank(' 奇函数 ','奇函数','text'))

    def test_manual_review_persisted_without_mastery(self):
        state,q=self.force_question('FILL_TEST');before=calculate_knowledge_mastery('TEST','K001')
        state=submit_training_answer('TEST',state['id'],q['id'],'无法安全解析',10.)
        answer=state['answers'][-1]
        self.assertEqual(answer['submission_status'],'needs_manual_review');self.assertIsNone(answer['is_correct'])
        self.assertEqual(before,calculate_knowledge_mastery('TEST','K001'))
        with closing(get_connection()) as c:
            self.assertEqual(c.execute('SELECT status FROM answer_review_requests').fetchone()[0],'needs_manual_review')
        summary=get_training_session_summary(state['id'])
        self.assertEqual(summary['pending_fill_blank'],1);self.assertIsNone(summary['accuracy'])

    def test_pending_fill_gate_nonnull_tamper(self):
        state,q=self.force_question('FILL_TEST')
        state=submit_training_answer('TEST',state['id'],q['id'],'不支持的格式',10.)
        with closing(get_connection()) as c,c:c.execute('UPDATE attempts SET is_correct=1 WHERE id=?',(state['answers'][-1]['attempt_id'],))
        self.assertEqual(calculate_knowledge_mastery('TEST','K001')['attempt_count'],0)

    def test_subjective_text_pending(self):
        state,q=self.force_question('SUBJECT_TEST')
        state=submit_training_answer('TEST',state['id'],q['id'],'先检查函数对应关系。',10.)
        with closing(get_connection()) as c:
            r=c.execute('SELECT * FROM subjective_submissions').fetchone()
            self.assertEqual(r['text_answer'],'先检查函数对应关系。');self.assertIsNone(r['score'])
            self.assertEqual(r['status'],'submitted_pending_review');self.assertIsNone(r['review_source'])
        self.assertEqual(calculate_knowledge_mastery('TEST','K001')['attempt_count'],0)

    def test_subjective_image_reference(self):
        data=BytesIO();Image.new('RGB',(12,12),'white').save(data,format='PNG')
        state,q=self.force_question('SUBJECT_TEST')
        with patch('services.handwriting_recognition.recognize_math_image',side_effect=AssertionError('No OCR')):
            state=submit_training_answer('TEST',state['id'],q['id'],'',10.,answer_payload={'image_bytes':data.getvalue()})
        with closing(get_connection()) as c:
            r=c.execute('SELECT * FROM subjective_submissions').fetchone();self.assertTrue(Path(r['attachment_path']).is_file())
            self.assertEqual(Path(r['attachment_path']).suffix,'.png');self.assertIsNone(r['score'])
            self.assertNotIn('image_bytes',json.dumps(state['answers'][-1]))

    def test_profile_and_feedback_pending_counts(self):
        state,q=self.force_question('SUBJECT_TEST')
        submit_training_answer('TEST',state['id'],q['id'],'未评分解答。',10.)
        counts=pending_counts('TEST');self.assertEqual(counts['K001']['subjective'],1)
        point=calculate_knowledge_mastery('TEST','K001')
        profile=build_profile_data([point],pending_by_point=counts)
        self.assertEqual(profile['overview']['total_attempts'],0);self.assertEqual(profile['overview']['pending_total'],1)
        context=build_feedback_context('TEST');self.assertEqual(context['pending_work']['subjective'],1)

    def test_renderer_pending_and_subquestions(self):
        st=MagicMock()
        with patch('services.question_renderer.render_math_text') as render:
            render_question(st,subjective());self.assertEqual(render.call_count,3)
        render_feedback(st,{'is_correct':None,'submission_status':'needs_manual_review'})
        st.warning.assert_called_once();st.error.assert_not_called()

    def test_mixed_types_deterministic(self):
        pool=[{'question_type':k} for k in ('single_choice','multiple_choice','fill_blank','subjective')]
        history=[]
        for _ in range(12):
            kind,ratios=select_question_type(pool,history,.9);history.append({'question_type':kind})
        self.assertEqual(set(a['question_type'] for a in history),set(q['question_type'] for q in pool))
        self.assertEqual(question_type_ratios(.84)['subjective'],.30);self.assertEqual(question_type_ratios(.85)['subjective'],.45)

    def test_exposure_source_and_variant(self):
        a={'id':'A','source_fingerprint':'same','variant_fingerprint':'v','source_file':'s','source_locator':'paragraphs 1–5'}
        b={**a,'id':'B','source_locator':'paragraphs 3–7'}
        self.assertTrue(exposure_tokens(a)&exposure_tokens(b))

    def test_real_approved_import_backup_idempotence_history_v1(self):
        record_attempt('HISTORY','Q001','D',1,2.)
        with closing(get_connection()) as c:before=[tuple(r) for r in c.execute('SELECT * FROM attempts')]
        result=integrate(self.path)
        self.assertTrue(Path(result['backup']).is_file());self.assertEqual(result['import']['inserted'],61)
        self.assertEqual(result['repeat_import']['inserted'],0)
        with closing(get_connection()) as c:self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM attempts')])
        self.assertEqual(len(get_training_questions(self.path,taxonomy_version='function_v1')),6)

    def test_failed_import_rolls_back_questions(self):
        rows=[multi(id='ROLLBACK_A',stem='题目一：哪些对应关系在实数域中表示函数？')]
        # Force a later insert to fail after a valid first insertion.
        rows.append(multi(id='Q001',stem='题目二：哪些对应关系在实数域中表示函数？'))
        with closing(get_connection()) as c:before=c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        with self.assertRaises(Exception):activate_training_questions(rows,database_path=self.path)
        with closing(get_connection()) as c:
            self.assertEqual(before,c.execute('SELECT COUNT(*) FROM questions').fetchone()[0])
            self.assertIsNone(c.execute("SELECT id FROM questions WHERE id='ROLLBACK_A'").fetchone())

    def test_streamlit_fill_manual_review(self):
        state,q=self.force_question('FILL_TEST',student='S001')
        app=AppTest.from_file(str(ROOT/'app.py')).run();app.switch_page('pages/training.py').run()
        next(w for w in app.text_input if w.label=='请输入填空答案').set_value('无法解析').run()
        next(b for b in app.button if b.label=='提交答案').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('needs_manual_review' in w.value for w in app.warning))

    def test_streamlit_subjective_subquestions_pending(self):
        state,q=self.force_question('SUBJECT_TEST',student='S001')
        app=AppTest.from_file(str(ROOT/'app.py')).run();app.switch_page('pages/training.py').run()
        self.assertFalse(app.exception);self.assertTrue(any('总分' in w.value for w in app.markdown))
        app.text_area[0].set_value('解题过程先由定义开始。').run()
        next(b for b in app.button if b.label=='提交答案').click().run()
        self.assertFalse(app.exception);self.assertTrue(any('待评阅' in w.value for w in app.success))


class ApprovalAuditTests(unittest.TestCase):
    def test_user_review_explicit_and_candidates_preserved(self):
        rows=load_approved();self.assertEqual(len(rows),61)
        for q in rows:
            self.assertEqual(q['reviewed_by'],'manual_user');self.assertIn(NOTE,q['review_notes'])
        for kind in ('multiple_choice','fill_blank','subjective'):
            candidates=[json.loads(s) for s in (ROOT/f'data/question_bank/candidates/function_{kind}_batch_001.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all(q['quality_status']=='reviewed' for q in candidates))
