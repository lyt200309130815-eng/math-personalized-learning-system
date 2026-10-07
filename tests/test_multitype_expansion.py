"""V1.0D.1 objective evaluation, isolated activation and source artifact checks."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from zipfile import ZipFile

from init_db import initialize_database
from database.database import get_connection, get_approved_questions
from database.taxonomy_migration import migrate_function_v2
from database.four_type import migrate_four_type
from scripts.function_v2_dry_run import load_gold
from scripts.inspect_multitype_sources import protected_snapshot
from services.answer_evaluator import evaluate_question, evaluate_fill_blank, evaluate_answer_result
from services.question_validator import validate_candidate, content_fingerprint
from services.question_importer import import_questions, activate_training_questions
from services.question_renderer import render_answer_input, read_answer_input
from services.adaptive_training import start_training_session, get_next_question, submit_training_answer
from services.mastery import calculate_knowledge_mastery
from question_bank_helpers import approved, candidate
from test_multi_type import typed_fixture
import test_multi_type

ROOT=Path(__file__).resolve().parents[1]


def multi(**changes):
    q=approved(id='MULTI_TEST',question_type='multiple_choice',primary_knowledge_point_id='K001',
               stem='以下哪些式子在实数域上表示函数？请选择所有正确选项。',
               options={'A':'y=x','B':'y=x^2','C':'x=y^2','D':'x=1'},
               explanation='每个实数 x 对应唯一的 y 时才是函数，因此 A、B 正确。',correct_answers=['A','B'])
    q.pop('answer');q.update(changes);q['fingerprint']=content_fingerprint(q)
    return q


def subjective():
    q=typed_fixture('subjective',sub_questions=[{'id':'1','stem':'说明唯一对应','max_score':2},
                                               {'id':'2','stem':'写出定义域','max_score':2}],
                    rubric=[{'sub_question':'1','criterion':'说明唯一对应关系','score':2},
                            {'sub_question':'2','criterion':'写出定义域 R','score':2}],
                    rubric_source='derived_for_system',reference_answers_by_subquestion={'1':'唯一对应。','2':'R。'})
    return q


class ExpansionEvaluationTests(unittest.TestCase):
    def test_multiple_exact_set(self):
        self.assertTrue(evaluate_question(multi(),['A','B']))
        self.assertFalse(evaluate_question(multi(),['A']))
        self.assertFalse(evaluate_question(multi(),['A','B','C']))

    def test_multiple_order(self):
        self.assertTrue(evaluate_question(multi(),['B','A']))
        self.assertTrue(evaluate_question(multi(),'["B", "A"]'))

    def test_multiple_invalid(self):
        for answer in ([],['E'],'[invalid'):
            with self.assertRaises(ValueError):evaluate_question(multi(),answer)

    def test_numeric(self):
        self.assertTrue(evaluate_fill_blank('0.5','1/2','numeric'))
        self.assertFalse(evaluate_fill_blank('0.50001','1/2','numeric'))

    def test_expression(self):
        self.assertTrue(evaluate_fill_blank('(x-1)(x+1)','x^2-1','expression'))

    def test_interval(self):
        self.assertTrue(evaluate_fill_blank('[0.5,2)','[1/2,2)','interval'))
        self.assertFalse(evaluate_fill_blank('[0.5,2]','[1/2,2)','interval'))

    def test_set(self):
        self.assertTrue(evaluate_fill_blank('{2,0.5,2}','{1/2,2}','set'))
        self.assertTrue(evaluate_fill_blank('∅','{}','set'))
        self.assertFalse(evaluate_fill_blank('{1,2}','{1,3}','set'))

    def test_manual_review(self):
        q=typed_fixture()
        for answer in ('1/0','__import__(os)','{x|x>1}'):
            result=evaluate_answer_result(q,answer)
            self.assertEqual(result,{'status':'needs_manual_review','is_correct':None})

    def test_expression_domain_not_cancelled(self):
        q=typed_fixture(answer_expression='1',accepted_answers=['1'],answer_type='expression')
        self.assertEqual(evaluate_answer_result(q,'x/x')['status'],'needs_manual_review')

    def test_subjective_pending(self):
        self.assertEqual(evaluate_answer_result(subjective(),'未完成'),{'status':'pending','is_correct':None})

    def test_validator_four_types(self):
        for q in (approved(),multi(),typed_fixture(),subjective()):
            self.assertTrue(validate_candidate(q)['can_approve'],validate_candidate(q))

    def test_multiple_contract(self):
        for changes in ({'correct_answers':['A']},{'correct_answers':['A','A']},{'answer':'A'},{'options':{'A':'x'}}):
            self.assertFalse(validate_candidate(multi(**changes))['valid'])

    def test_subquestion_structure(self):
        q=subjective();q['sub_questions'][1]['id']='1';q['fingerprint']=content_fingerprint(q)
        self.assertFalse(validate_candidate(q)['valid'])

    def test_rubric_references(self):
        q=subjective();q['rubric'][0]['sub_question']='3';q['fingerprint']=content_fingerprint(q)
        self.assertFalse(validate_candidate(q)['valid'])

    def test_subquestion_score(self):
        q=subjective();q['sub_questions'][0]['max_score']=3;q['fingerprint']=content_fingerprint(q)
        self.assertFalse(validate_candidate(q)['valid'])

    def test_reference_subquestion_mapping(self):
        q=subjective();q['reference_answers_by_subquestion'].pop('2');q['fingerprint']=content_fingerprint(q)
        self.assertFalse(validate_candidate(q)['valid'])

    def test_formula_loss_blocked(self):
        q=candidate(stem='已知函数 f(x)=，求函数的定义域。')
        self.assertFalse(validate_candidate(q)['can_approve'])

    def test_missing_image_blocked(self):
        self.assertFalse(validate_candidate(candidate(stem='函数图象如图所示，求对应函数的零点。'))['can_approve'])

    def test_fingerprint_types_and_set_order(self):
        a=multi();b=multi(correct_answers=['B','A'])
        self.assertEqual(a['fingerprint'],b['fingerprint'])
        c=deepcopy(a);c['correct_answers']=['A','C']
        self.assertNotEqual(content_fingerprint(a),content_fingerprint(c))
        c=deepcopy(a);c['question_type']='single_choice';c['answer']='A'
        self.assertNotEqual(content_fingerprint(a),content_fingerprint(c))

    def test_multiple_renderer(self):
        st=MagicMock();render_answer_input(st,multi(),'a')
        self.assertEqual(st.checkbox.call_count,4);st.radio.assert_not_called()
        st.session_state={'a_B':True,'a_A':True}
        self.assertTrue(evaluate_question(multi(),read_answer_input(st,multi(),'a')[0]))


class ExpansionIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'four.db'
        initialize_database(self.path);migrate_function_v2(self.path,load_gold())
        env=patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2'})
        env.start();self.addCleanup(env.stop)
        migrate_four_type(self.path)

    force_question=test_multi_type.MultiTypeIntegrationTests.force_question

    def test_importer_four_types(self):
        rows=[approved(),multi(),typed_fixture(),subjective()]
        self.assertEqual(import_questions(rows,database_path=self.path)['inserted'],4)
        self.assertEqual(activate_training_questions(rows,database_path=self.path)['inserted'],4)
        got={q['id']:q for q in get_approved_questions(database_path=self.path)}
        self.assertEqual(got['MULTI_TEST']['correct_answers'],['A','B'])
        self.assertEqual(got['SUBJECT_TEST']['sub_questions'],subjective()['sub_questions'])

    def test_reviewed_rejected_before_mutation(self):
        q=multi(quality_status='reviewed');before=self.path.read_bytes()
        self.assertEqual(import_questions([q],database_path=self.path)['rejected'],1)
        with self.assertRaises(ValueError):activate_training_questions([q],database_path=self.path)
        self.assertEqual(before,self.path.read_bytes())

    def test_migration_historical_attempts_preserved(self):
        with closing(get_connection()) as conn:
            before=[tuple(r) for r in conn.execute('SELECT * FROM attempts')]
        self.assertFalse(migrate_four_type(self.path)['applied'])
        with closing(get_connection()) as conn:
            self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM attempts')])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_multiple_training_submission(self):
        activate_training_questions([multi()],database_path=self.path)
        state,q=self.force_question('MULTI_TEST')
        state=submit_training_answer('TEST',state['id'],q['id'],'["B","A"]',10.)
        self.assertEqual(state['answers'][-1]['is_correct'],1)
        self.assertEqual(calculate_knowledge_mastery('TEST','K001')['attempt_count'],1)

    def test_set_training_submission(self):
        q=typed_fixture(answer_expression=None,canonical_answer='{1/2,2}',accepted_answers=['{1/2,2}'],answer_type='set')
        activate_training_questions([q],database_path=self.path)
        state,current=self.force_question(q['id'])
        state=submit_training_answer('TEST',state['id'],q['id'],'{2,0.5}',10.)
        self.assertEqual(state['answers'][-1]['is_correct'],1)

    def test_subjective_does_not_pollute_mastery(self):
        activate_training_questions([subjective()],database_path=self.path)
        state,q=self.force_question('SUBJECT_TEST');before=calculate_knowledge_mastery('TEST','K001')
        state=submit_training_answer('TEST',state['id'],q['id'],'只有一段未评分答案。',10.)
        self.assertIsNone(state['answers'][-1]['is_correct'])
        self.assertEqual(before,calculate_knowledge_mastery('TEST','K001'))

    def test_manual_review_no_attempt(self):
        activate_training_questions([typed_fixture()],database_path=self.path)
        state,q=self.force_question('FILL_TEST')
        with self.assertRaises(ValueError):submit_training_answer('TEST',state['id'],q['id'],'不支持的答案',10.)
        with closing(get_connection()) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],0)

    def test_multiple_natural_selection(self):
        activate_training_questions([multi()],database_path=self.path)
        state=start_training_session('TEST',target_knowledge_point_id='K001')
        with patch('services.adaptive_training._eligible',return_value=[multi()]):
            q=get_next_question('TEST',state['id'])
        self.assertEqual(q['question_type'],'multiple_choice')

    def test_multiple_streamlit_submission(self):
        activate_training_questions([multi()],database_path=self.path)
        state,q=self.force_question('MULTI_TEST',student='S001')
        app=test_multi_type.AppTest.from_file(str(ROOT/'app.py')).run()
        app.switch_page('pages/training.py').run()
        self.assertFalse(app.exception)
        for letter in ('B','A'):
            next(w for w in app.checkbox if w.label.startswith(letter+'.')).check().run()
        next(b for b in app.button if b.label=='提交答案').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['adaptive_training_state']['answers'][-1]['is_correct'],1)

    def test_exposure_without_submission_avoided(self):
        other=multi(id='NEW_MULTI',stem='以下四个对应关系中，哪些在实数域上表示函数？请选择正确选项。')
        activate_training_questions([multi(),other],database_path=self.path)
        old,q=self.force_question('MULTI_TEST')
        from services.adaptive_training import end_training_session
        end_training_session('TEST',old['id'])
        state=start_training_session('TEST',target_knowledge_point_id='K001')
        with patch('services.adaptive_training._eligible',return_value=[multi(),other]):
            selected=get_next_question('TEST',state['id'])
        self.assertEqual(selected['id'],'NEW_MULTI')


class ExpansionArtifactTests(unittest.TestCase):
    def load_batches(self):
        result=[]
        for kind,batch in [('multiple_choice','001'),('fill_blank','002'),('subjective','002')]:
            stem=f'function_{kind}_batch_{batch}'
            path=ROOT/f'data/question_bank/candidates/{stem}.jsonl'
            self.assertEqual(path.read_bytes(),(ROOT/f'data/question_bank/review_required/{stem}.jsonl').read_bytes())
            result.extend(json.loads(s) for s in path.read_text(encoding='utf-8').splitlines())
        return result

    def test_all_reviewed_reliable(self):
        rows=self.load_batches()
        self.assertEqual(len(rows),len({q['fingerprint'] for q in rows}))
        for q in rows:
            self.assertEqual(q['quality_status'],'reviewed')
            self.assertEqual(q['extraction_status'],'complete')
            self.assertTrue(validate_candidate(q,check_formulas=False)['can_approve'],q['id'])

    def test_no_old_approved_repeats(self):
        gold=load_gold();fingerprints={q['fingerprint'] for q in gold}
        source_ranges={(q['source_file'],q['source_locator']) for q in gold}
        for q in self.load_batches():
            self.assertNotIn(q['fingerprint'],fingerprints)
            self.assertNotIn((q['source_file'],q['source_locator']),source_ranges)

    def test_word_native_math_and_review_fields(self):
        for kind,batch in [('multiple_choice','001'),('fill_blank','002'),('subjective','002')]:
            with ZipFile(ROOT/f'reports/function_{kind}_batch_{batch}_可读版.docx') as z:
                self.assertIsNone(z.testzip());xml=z.read('word/document.xml').decode()
                self.assertIn('oMath',xml);self.assertIn('审核记录',xml)

    def test_production_migration_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pretend_production.db'
            path.write_bytes(b'protected')
            with patch('database.taxonomy_migration.DATABASE_PATH',path):
                with self.assertRaises(ValueError):migrate_four_type(path)
            self.assertEqual(path.read_bytes(),b'protected')

    def test_source_reproducibility(self):
        from services.source_extractors.docx_expansion_extractor import extract_expansion_questions
        groups={}
        for q in self.load_batches():groups.setdefault(q['source_file'],[]).append(q)
        for source,rows in groups.items():
            # Paths are part of IDs, so rescan with the same relative locator.
            extracted={q['id']:q for q in extract_expansion_questions(source)}
            for q in rows:self.assertEqual(q['fingerprint'],extracted[q['id']]['fingerprint'])
