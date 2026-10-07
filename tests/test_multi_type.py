"""Multi-type scoring, persistence, migration, review boundary and UI integration."""
from contextlib import closing
from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from zipfile import ZipFile

from PIL import Image
from streamlit.testing.v1 import AppTest
from init_db import initialize_database
from database.database import get_connection, get_approved_questions, record_attempt
from database.taxonomy_migration import migrate_function_v2
from database.training_sessions import load_session, save_session
from database.multi_type import migrate_multi_type
from scripts.function_v2_dry_run import load_gold
from services.answer_evaluator import evaluate_fill_blank, evaluate_question
from services.answer_attachments import save_answer_image
from services.handwriting_recognition import recognize_math_image
from services.question_validator import validate_candidate, content_fingerprint
from services.question_importer import import_questions, activate_training_questions, get_approved_questions as get_bank
from services.question_type_policy import select_question_type, question_type_ratios
from services.adaptive_training import start_training_session, get_next_question, submit_training_answer, get_training_session_summary
from services.mastery import calculate_knowledge_mastery
from services.training_support import retry_question, select_error_type
from services.question_renderer import read_answer_input
from question_bank_helpers import approved

ROOT = Path(__file__).resolve().parents[1]


def typed_fixture(kind='fill_blank',**changes):
    q=approved(id='FILL_TEST' if kind=='fill_blank' else 'SUBJECT_TEST',question_type=kind,
               stem='函数 f(x)=x+1，求 f(-1/2) 的值。' if kind=='fill_blank' else '函数 f(x)=x+1，说明对应关系并写出函数定义域。',
               explanation='代入 x=-1/2，可得函数值为 1/2。' if kind=='fill_blank' else '每个实数 x 对应唯一的 x+1，定义域为全体实数 R。',
               primary_knowledge_point_id='K001',
               source_locator='word/document.xml paragraphs 11–17' if kind=='fill_blank' else 'word/document.xml paragraphs 21–27')
    q.pop('options');q.pop('answer')
    if kind=='fill_blank':q.update(answer_expression='1/2',accepted_answers=['1/2','0.5'],answer_type='numeric')
    else:q.update(reference_answer='每个实数对应唯一函数值，定义域为 R。',solution_steps=['确认唯一对应关系。','定义域为 R。'],
                  rubric=[{'criterion':'说明唯一对应关系','score':2},{'criterion':'写出定义域 R','score':2}],max_score=4)
    q.update(changes)
    q['fingerprint']=content_fingerprint(q)
    return q


class EvaluatorTests(unittest.TestCase):
    def test_numeric_equivalence_exact(self):
        self.assertTrue(evaluate_fill_blank('0.5','1/2','numeric'))
        self.assertTrue(evaluate_fill_blank('2sqrt(3)','sqrt(12)','numeric'))
        self.assertFalse(evaluate_fill_blank('0.5000001','1/2','numeric'))
        self.assertTrue(evaluate_fill_blank('1e-3','1/1000','numeric'))

    def test_expression_equivalence(self):
        self.assertTrue(evaluate_fill_blank('(x-1)(x+1)','x^2-1','expression'))
        self.assertTrue(evaluate_fill_blank('x(x+1)','x^2+x','expression'))
        self.assertFalse(evaluate_fill_blank('x^2+1','x^2-1','expression'))

    def test_interval_endpoints_and_unions(self):
        self.assertTrue(evaluate_fill_blank('（-∞，0）∪（0，+∞）','(-oo,0) U (0,oo)','interval'))
        self.assertTrue(evaluate_fill_blank('[0.5,2)','[1/2,2)','interval'))
        self.assertFalse(evaluate_fill_blank('[0,1]','[0,1)','interval'))
        with self.assertRaises(ValueError):evaluate_fill_blank('[0,+∞]','[0,+∞)','interval')

    def test_invalid_input_never_executes(self):
        for value in ["__import__('os').system('echo BAD')",'x.__class__','[x for x in R]','1/0','x^999999','', 'sqrt(-1)']:
            with self.subTest(value=value),self.assertRaises(ValueError):evaluate_fill_blank(value,'1','numeric')

    def test_text_and_subjective(self):
        self.assertTrue(evaluate_fill_blank(' 奇函数 ','奇函数','text'))
        self.assertIsNone(evaluate_question(typed_fixture('subjective'),'随意内容'))

    def test_type_validation_and_rubric(self):
        for kind in ('single_choice','fill_blank','subjective'):
            q=approved() if kind=='single_choice' else typed_fixture(kind)
            self.assertTrue(validate_candidate(q)['can_approve'])
        for changes in ({'rubric':[]},{'max_score':-1},{'rubric':[{'criterion':'条件','score':float('nan')}]},
                        {'max_score':5},{'reference_answer':''}):
            self.assertFalse(validate_candidate(typed_fixture('subjective',**changes))['valid'])
        self.assertFalse(validate_candidate(typed_fixture(options={'A':'1'}))['valid'])
        self.assertFalse(validate_candidate(typed_fixture(answer_expression=None,accepted_answers=[]))['valid'])

    def test_deterministic_type_ratios(self):
        pool=[{'question_type':k} for k in question_type_ratios(1)]
        for score,expected in ((None,[5,4,1]),(.7,[5,9,6]),(.9,[4,7,9])):
            history=[]
            for _ in range(sum(expected)):
                kind,_=select_question_type(pool,history,score)
                history.append({'question_type':kind})
            self.assertEqual([sum(a['question_type']==k for a in history) for k in question_type_ratios(score)],expected)


class MultiTypeIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'multi.db'
        initialize_database(self.path)
        migrate_function_v2(self.path,load_gold())
        env=patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2'})
        env.start();self.addCleanup(env.stop)
        migrate_multi_type()

    def force_question(self,qid,student='TEST'):
        state=start_training_session(student,target_knowledge_point_id='K001')
        q=next(q for q in get_approved_questions('K001') if q['id']==qid)
        state.update(current_question=q,submitted=False,question_started_at=time.time(),selection_note='测试题型渲染',question_hint_count=0,question_retry_count=0)
        with closing(get_connection()) as conn,conn:
            sequence=conn.execute('SELECT COALESCE(MAX(sequence_no),0)+1 FROM training_session_questions WHERE session_id=?',(state['id'],)).fetchone()[0]
            conn.execute('INSERT INTO training_session_questions(session_id,question_id,sequence_no,difficulty) VALUES (?,?,?,?)',(state['id'],qid,sequence,q['difficulty']))
            save_session(conn,state)
        return state,q

    def test_legacy_rows_and_migration_idempotency(self):
        with closing(get_connection()) as conn:
            before=[tuple(r) for r in conn.execute('SELECT * FROM questions ORDER BY id')]
        self.assertFalse(migrate_multi_type()['applied'])
        with closing(get_connection()) as conn:
            self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM questions ORDER BY id')])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        q=get_approved_questions('K001')[0]
        self.assertEqual(q['question_type'],'single_choice')
        self.assertEqual(set(q['options']),set('ABCD'))

    def test_import_three_types_approved_only(self):
        rows=[approved(),typed_fixture(),typed_fixture('subjective')]
        result=import_questions(rows,database_path=self.path)
        self.assertEqual(result['inserted'],3)
        self.assertEqual(len(get_bank('K001',database_path=self.path)),2)
        activate_training_questions(rows,database_path=self.path)
        self.assertEqual(activate_training_questions(rows,database_path=self.path)['skipped'],3)
        fill=next(q for q in get_approved_questions('K001') if q['id']=='FILL_TEST')
        self.assertIsNone(fill['options'])
        self.assertEqual(fill['accepted_answers'],['$1/2$','0.5'])
        unapproved=typed_fixture(quality_status='reviewed')
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):activate_training_questions([unapproved],database_path=self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_fill_scoring_payload_mastery_and_retry(self):
        activate_training_questions([typed_fixture()],database_path=self.path)
        state,q=self.force_question('FILL_TEST')
        state=submit_training_answer('TEST',state['id'],q['id'],'1',10.)
        self.assertEqual(state['answers'][-1]['is_correct'],0)
        retry_question('TEST',state['id'])
        state=submit_training_answer('TEST',state['id'],q['id'],'0.5',10.)
        self.assertEqual(state['answers'][-1]['is_correct'],1)
        self.assertEqual(calculate_knowledge_mastery('TEST','K001')['attempt_count'],2)
        with closing(get_connection()) as conn:
            row=conn.execute('SELECT * FROM attempt_details ORDER BY attempt_id DESC LIMIT 1').fetchone()
            self.assertEqual(row['question_type'],'fill_blank')
            self.assertEqual(json.loads(row['answer_payload'])['text'],'0.5')

    def test_unscored_subjective_excluded_from_mastery_and_summary(self):
        activate_training_questions([typed_fixture('subjective')],database_path=self.path)
        state,q=self.force_question('SUBJECT_TEST')
        before=calculate_knowledge_mastery('TEST','K001')
        state=submit_training_answer('TEST',state['id'],q['id'],'定义域为 R，每个 x 对应唯一值。',10.)
        self.assertIsNone(state['answers'][-1]['is_correct'])
        self.assertEqual(before,calculate_knowledge_mastery('TEST','K001'))
        summary=get_training_session_summary(state['id'])
        self.assertEqual((summary['total'],summary['scored_total'],summary['pending_total']),(1,0,1))
        self.assertIsNone(summary['accuracy'])
        for fn,args in [(retry_question,()),(select_error_type,('K',))]:
            with self.assertRaises(ValueError):fn('TEST',state['id'],*args)
        with closing(get_connection()) as conn:
            row=conn.execute('SELECT * FROM attempt_details').fetchone()
            self.assertEqual(row['scoring_status'],'pending')

    def test_image_file_reference_without_ocr(self):
        data=BytesIO();Image.new('RGB',(10,10),'white').save(data,format='PNG')
        activate_training_questions([typed_fixture('subjective')],database_path=self.path)
        state,q=self.force_question('SUBJECT_TEST')
        with patch('services.handwriting_recognition.recognize_math_image',side_effect=AssertionError('No OCR')):
            state=submit_training_answer('TEST',state['id'],q['id'],'',10.,answer_payload={'image_bytes':data.getvalue()})
        payload=state['answers'][-1]['answer_payload']
        self.assertTrue(Path(payload['attachment_path']).is_file())
        self.assertNotIn('image_bytes',payload)
        self.assertEqual(recognize_math_image(payload['attachment_path'])['status'],'not_implemented')
        with self.assertRaises(ValueError):save_answer_image(b'not an image',database_path=self.path)

    def test_ui_fill_and_subjective_switch(self):
        for kind in ('fill_blank','subjective'):
            with self.subTest(kind=kind):
                activate_training_questions([typed_fixture(kind)],database_path=self.path)
                state,q=self.force_question('FILL_TEST' if kind=='fill_blank' else 'SUBJECT_TEST',student='S001')
                app=AppTest.from_file(str(ROOT/'app.py')).run()
                app.switch_page('pages/training.py').run()
                self.assertFalse(app.exception)
                self.assertFalse(app.radio)
                if kind=='fill_blank':
                    next(t for t in app.text_input if t.label=='请输入填空答案').set_value('0.5').run()
                else:
                    self.assertTrue(app.get('file_uploader'))
                    app.text_area[0].set_value('定义域为全体实数 R。').run()
                next(b for b in app.button if b.label=='提交答案').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(app.session_state['adaptive_training_state']['submitted'])
                next(b for b in app.button if b.label=='结束本轮训练').click().run()
                self.assertFalse(app.exception)

    def test_invalid_fill_syntax_does_not_write(self):
        activate_training_questions([typed_fixture()],database_path=self.path)
        state,q=self.force_question('FILL_TEST')
        with self.assertRaises(ValueError):submit_training_answer('TEST',state['id'],q['id'],'1/0',2.)
        with closing(get_connection()) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],0)

    def test_pending_status_gates_even_nonnull_correctness(self):
        activate_training_questions([typed_fixture('subjective')],database_path=self.path)
        state,q=self.force_question('SUBJECT_TEST')
        state=submit_training_answer('TEST',state['id'],q['id'],'定义域 R。',10.)
        with closing(get_connection()) as conn,conn:
            conn.execute('UPDATE attempts SET is_correct=1 WHERE id=?',(state['answers'][-1]['attempt_id'],))
        self.assertEqual(calculate_knowledge_mastery('TEST','K001')['attempt_count'],0)

    def test_high_mastery_naturally_selects_subjective_without_llm(self):
        q=get_approved_questions('K001')[0]
        for _ in range(12):record_attempt('TEST',q['id'],q['answer'],1,10.)
        activate_training_questions([typed_fixture(),typed_fixture('subjective')],database_path=self.path)
        with patch('services.feedback.generate_text',side_effect=AssertionError('No LLM for correctness')):
            state=start_training_session('TEST',target_knowledge_point_id='K001')
            kinds=[]
            for _ in range(3):
                current=get_next_question('TEST',state['id'])
                kind=current['question_type'];kinds.append(kind)
                answer=current['answer'] if kind=='single_choice' else '0.5' if kind=='fill_blank' else '定义域为 R。'
                state=submit_training_answer('TEST',state['id'],current['id'],answer,10.)
            self.assertIn('subjective',kinds)
            self.assertEqual(calculate_knowledge_mastery('TEST','K001')['attempt_count'],14)

    def test_migration_failure_rolls_back_rows_and_links(self):
        from database.multi_type import SCHEMA
        with closing(get_connection()) as conn,conn:
            conn.execute("DELETE FROM schema_migrations WHERE id='v1_0d_multi_type'")
            conn.execute('DROP TRIGGER validate_attempt_insert')
            conn.execute('DROP TRIGGER validate_attempt_update')
            before=[tuple(r) for r in conn.execute('SELECT * FROM questions ORDER BY id')]
        with patch('database.multi_type.SCHEMA',SCHEMA+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):migrate_multi_type()
        with closing(get_connection()) as conn:
            self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM questions ORDER BY id')])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_uploaded_input_abstraction(self):
        st=MagicMock()
        upload=MagicMock();upload.getvalue.return_value=b'image bytes'
        st.session_state={'answer':'过程','answer_image':upload}
        answer,payload=read_answer_input(st,typed_fixture('subjective'),'answer')
        self.assertEqual(answer,'过程')
        self.assertEqual(payload['image_bytes'],b'image bytes')


class BatchArtifactTests(unittest.TestCase):
    def test_candidates_reproduce_source_boundaries_and_rubrics(self):
        from services.source_extractors.docx_multi_type_extractor import extract_multi_type_questions
        from collections import defaultdict
        groups=defaultdict(list)
        for kind in ('fill_blank','subjective'):
            p=ROOT/'data/question_bank/candidates'/f'function_{kind}_batch_001.jsonl'
            for line in p.read_text(encoding='utf-8').splitlines():
                row=json.loads(line);groups[row['source_file']].append(row)
        for source,rows in groups.items():
            extracted={r['id']:r for r in extract_multi_type_questions(source)}
            for row in rows:
                self.assertEqual(row['fingerprint'],extracted[row['id']]['fingerprint'])
                self.assertEqual(row['explanation'],extracted[row['id']]['explanation'])

    def test_reviewed_batches_no_options_and_source_integrity(self):
        for kind,minimum,maximum in [('fill_blank',20,30),('subjective',15,20)]:
            p=ROOT/'data/question_bank/candidates'/f'function_{kind}_batch_001.jsonl'
            rows=[json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()]
            self.assertGreaterEqual(len(rows),minimum);self.assertLessEqual(len(rows),maximum)
            self.assertEqual(len(rows),len({r['fingerprint'] for r in rows}))
            for row in rows:
                self.assertEqual(row['quality_status'],'reviewed')
                self.assertEqual(row['question_type'],kind)
                self.assertNotIn('options',row)
                self.assertTrue(validate_candidate(row,check_formulas=False)['can_approve'])
                self.assertTrue((ROOT/row['source_file']).is_file())
            docx=ROOT/'reports'/f'function_{kind}_batch_001_可读版.docx'
            with ZipFile(docx) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(b'oMath',archive.read('word/document.xml'))
