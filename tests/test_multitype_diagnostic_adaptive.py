"""V1.0D.3 coverage, pending evidence and exposure on disposable databases."""
from collections import Counter
from contextlib import closing
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image
from streamlit.testing.v1 import AppTest
from database.database import get_connection, get_approved_questions, get_training_questions, record_attempt
from services.diagnostic import start_diagnostic, submit_diagnostic_answer, generate_diagnostic_test
from services.diagnostic_mix import plan_questions, TYPES
from services.adaptive_training import start_training_session, get_next_question, submit_training_answer, exposure_tokens
from services.mastery import calculate_student_mastery
from services.question_type_policy import select_question_type, question_type_ratios
from services.question_renderer import render_answer_input

ROOT = Path(__file__).resolve().parents[1]


class MixedDiagnosticTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)/'copy.db'
        with closing(get_connection(ROOT/'math_ai.db', read_only=True)) as src, closing(get_connection(self.path)) as dst:
            src.backup(dst)
        env = patch.dict(os.environ, {'MATH_AI_DATABASE_PATH':str(self.path), 'ACTIVE_TAXONOMY_VERSION':'function_v2', 'OPENAI_API_KEY':'', 'DEEPSEEK_API_KEY':''})
        env.start(); self.addCleanup(env.stop)
        self.student = 'D3_TEST_FRESH'

    def complete(self):
        state = start_diagnostic(self.student)
        while not state['diagnostic_completed']:
            q = state['current_question']; kind = q['question_type']
            answer = q['answer'] if kind == 'single_choice' else json.dumps(q['correct_answers']) if kind == 'multiple_choice' else q['canonical_answer'] if kind == 'fill_blank' else '由定义出发，逐步列式求解。'
            state = submit_diagnostic_answer(state['id'], q['id'], answer, answer_time=2)
        return state

    def test_18_mixed(self):
        state = self.complete(); self.assertEqual(state['result']['total'],18)
        self.assertEqual(state['result']['question_type_counts'],dict(zip(TYPES,(6,2,7,3))))

    def test_choice_ceiling(self):
        state=generate_diagnostic_test(self.student); mix=state['target_question_type_counts']
        self.assertLessEqual((mix['single_choice']+mix['multiple_choice'])/18,.55)

    def test_blank_minimum(self):
        self.assertGreaterEqual(generate_diagnostic_test(self.student)['target_question_type_counts']['fill_blank']/18,.3)

    def test_subjective_available(self):
        self.assertGreaterEqual(generate_diagnostic_test(self.student)['target_question_type_counts']['subjective'],1)

    def test_full_knowledge_coverage(self):
        state=self.complete(); self.assertEqual(len({a['knowledge_point_id'] for a in state['answers']}),15)

    def test_blank_no_options(self):
        self.assertTrue(all(not q['options'] for q in get_approved_questions() if q['question_type']=='fill_blank'))

    def test_subjective_no_options(self):
        self.assertTrue(all(not q['options'] for q in get_approved_questions() if q['question_type']=='subjective'))

    def force_diagnostic(self,kind):
        state=start_diagnostic(self.student,restart=True)
        q=next(q for q in state['pool'] if q['question_type']==kind)
        state['current_question']=q
        from database.diagnostic import save_state
        with closing(get_connection()) as c,c: save_state(c,state)
        return state,q

    def test_blank_evaluator(self):
        state,q=self.force_diagnostic('fill_blank')
        saved=submit_diagnostic_answer(state['id'],q['id'],q['canonical_answer'])
        self.assertEqual(saved['answers'][-1]['is_correct'],1)

    def test_unparseable_no_mastery(self):
        state,q=self.force_diagnostic('fill_blank'); before=calculate_student_mastery(self.student)
        saved=submit_diagnostic_answer(state['id'],q['id'],'无法安全解析')
        self.assertEqual(saved['answers'][-1]['submission_status'],'needs_manual_review')
        self.assertEqual(calculate_student_mastery(self.student),before)

    def test_subjective_pending_no_mastery(self):
        state,q=self.force_diagnostic('subjective'); before=calculate_student_mastery(self.student)
        saved=submit_diagnostic_answer(state['id'],q['id'],'先列出条件。')
        self.assertIsNone(saved['answers'][-1]['is_correct']); self.assertEqual(calculate_student_mastery(self.student),before)
        with closing(get_connection()) as c:
            r=c.execute('SELECT * FROM subjective_submissions WHERE student_id=?',(self.student,)).fetchone()
            self.assertEqual(r['status'],'submitted_pending_review'); self.assertIsNone(r['score'])

    def test_diagnostic_upload(self):
        state,q=self.force_diagnostic('subjective'); image=BytesIO(); Image.new('RGB',(30,20),'white').save(image,format='PNG')
        saved=submit_diagnostic_answer(state['id'],q['id'],'',answer_payload={'image_bytes':image.getvalue()})
        self.assertTrue(Path(saved['answers'][-1]['answer_payload']['attachment_path']).is_file())

    def test_result_excludes_pending(self):
        state=self.complete(); r=state['result']; self.assertEqual(r['scored_total'],15); self.assertEqual(r['correct'],15); self.assertEqual(r['pending_subjective'],3)

    def test_recent_diagnostic_exposure(self):
        state=self.complete(); diagnosed={a['question_id'] for a in state['answers']}
        train=start_training_session(self.student,target_knowledge_point_id='K002')
        q=get_next_question(self.student,train['id']); self.assertIsNotNone(q); self.assertNotIn(q['id'],diagnosed)
        identities={q['id']:exposure_tokens(q) for q in state['pool']}
        self.assertFalse(exposure_tokens(q) & set().union(*(identities[k] for k in diagnosed)))

    def test_shortage_fallback(self):
        pool=[q for q in get_approved_questions() if q['question_type']=='single_choice']
        ids,mix,limits=plan_questions(pool,18); self.assertEqual(len(ids),18); self.assertEqual(mix['single_choice'],18); self.assertTrue(limits)

    def test_function_v1_fallback(self):
        self.assertEqual(len(get_training_questions(taxonomy_version='function_v1')),6)

    def test_legacy_active_pool_upgrade_preserves_attempts(self):
        from database.diagnostic import save_state
        from services.diagnostic import restore_diagnostic
        state=start_diagnostic(self.student)
        q=state['current_question']
        state=submit_diagnostic_answer(state['id'],q['id'],q['answer'])
        recorded=list(state['answers'])
        state.pop('mix_policy_version')
        state['pool']=[q for q in state['pool'] if q['question_type']=='single_choice']
        with closing(get_connection()) as c,c: save_state(c,state)
        upgraded=restore_diagnostic(self.student)
        self.assertEqual(upgraded['answers'],recorded)
        self.assertEqual(upgraded['mix_policy_version'],'V1.0D.3')
        self.assertIn('fill_blank',{q['question_type'] for q in upgraded['pool']})

    def test_subjective_does_not_adjust_difficulty(self):
        from database.training_sessions import save_session
        self.complete()
        state=start_training_session(self.student,target_knowledge_point_id='K002')
        q=next(q for q in get_approved_questions('K002') if q['question_type']=='subjective')
        state.update(current_question=q,submitted=False,question_hint_count=0,question_retry_count=0)
        with closing(get_connection()) as c,c:
            c.execute('INSERT INTO training_session_questions(session_id,question_id,sequence_no,difficulty) VALUES (?,?,1,?)',(state['id'],q['id'],q['difficulty']))
            save_session(c,state)
        before=(state['difficulty'],state['correct_streak'],state['wrong_streak'])
        saved=submit_training_answer(self.student,state['id'],q['id'],'先列条件再分步求解。',2)
        self.assertEqual(before,(saved['difficulty'],saved['correct_streak'],saved['wrong_streak']))

    def test_fresh_adjacent_precedes_recent_basic_question(self):
        self.complete()
        state=start_training_session(self.student,target_knowledge_point_id='K004')
        basic=[q for q in get_approved_questions('K004') if q['difficulty']==2]
        for i,q in enumerate(basic):
            answer=q['answer'] if q['question_type']=='single_choice' else '先列条件。'
            if q['question_type']=='single_choice': record_attempt(self.student,q['id'],answer,int(i%2==0),2)
        # D2 questions have now all been exposed; D3 blanks remain fresh.
        with patch('services.adaptive_training._difficulty_cap',return_value=2):
            q=get_next_question(self.student,state['id'])
        self.assertEqual(q['difficulty'],3)
        self.assertNotIn(q['id'],{r['id'] for r in basic})

    def test_diagnostic_page_mixed_inputs(self):
        self.student='S001'
        for kind in ('fill_blank','subjective'):
            with self.subTest(kind=kind):
                state,q=self.force_diagnostic(kind)
                app=AppTest.from_file(str(ROOT/'app.py')).run()
                app.switch_page('pages/diagnostic.py').run()
                self.assertFalse(app.exception); self.assertEqual(len(app.radio),0)
                self.assertTrue(app.text_area if kind=='subjective' else [w for w in app.text_input if w.label=='请输入填空答案'])


class SessionTypePolicyTests(unittest.TestCase):
    pool=[{'question_type':k} for k in TYPES]

    def mix(self,score,n=8):
        answers=[]
        for _ in range(n):
            kind,_=select_question_type(self.pool,answers,score); answers.append({'question_type':kind})
        return Counter(a['question_type'] for a in answers)

    def test_session_diversity(self): self.assertGreaterEqual(len(self.mix(None)),2)
    def test_high_mastery_subjective(self): self.assertGreater(self.mix(.9)['subjective'],self.mix(.1)['subjective'])
    def test_low_mastery_foundation(self): self.assertGreaterEqual(self.mix(None)['single_choice']+self.mix(None)['multiple_choice'],3)
    def test_six_has_blank(self): self.assertGreaterEqual(self.mix(.7,6)['fill_blank'],1)
    def test_weights(self):
        for score,expected in ((None,(.5,.4,.1)),(.4,(.35,.45,.2)),(.7,(.25,.45,.3)),(.85,(.2,.35,.45))):
            self.assertEqual(tuple(question_type_ratios(score).values()),expected)
    def test_checkbox_renderer(self):
        st=MagicMock(); render_answer_input(st,{'question_type':'multiple_choice','options':dict.fromkeys('ABCD','内容')},'answer')
        self.assertEqual(st.checkbox.call_count,4); st.radio.assert_not_called()


if __name__=='__main__': unittest.main()
