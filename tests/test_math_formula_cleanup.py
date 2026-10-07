"""Deterministic normalization, quarantine, rendering and protected DB cleanup."""
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock

from streamlit.testing.v1 import AppTest
from database.database import get_connection,get_approved_questions
from database.formula_status import store_status
from services.math_normalizer import normalize_math_text,normalize_math_expression,validate_math_expression,audit_question,FormulaManualReview,evaluator_math_text
from services.math_text import math_markdown,render_math_text
from services.question_renderer import render_answer_input
from services.answer_evaluator import evaluate_fill_blank
from services.diagnostic import generate_diagnostic_test,start_diagnostic,restore_diagnostic
from services.adaptive_training import start_training_session,get_next_question
from services.question_validator import validate_candidate
from services.question_importer import activate_training_questions
from scripts.audit_math_formulas import apply,digest
from scripts.integrate_multitype_production import snapshot

ROOT=Path(__file__).resolve().parents[1]


class MathNormalizationTests(unittest.TestCase):
    def test_exponent(self): self.assertEqual(normalize_math_expression('a^(2)'), 'a^{2}')
    def test_expression_exponent(self): self.assertEqual(normalize_math_expression('x^(m+n)'), 'x^{m+n}')
    def test_fraction(self): self.assertEqual(normalize_math_expression('(2)/(3)'),r'\frac{2}{3}')
    def test_sqrt(self): self.assertEqual(normalize_math_expression('sqrt(x)'),r'\sqrt{x}')
    def test_explicit_root(self): self.assertEqual(normalize_math_expression('root(3,x)'),r'\sqrt[3]{x}')
    def test_nested_script(self): self.assertEqual(normalize_math_expression('((2)/(3))^(x^(2))'),r'(\frac{2}{3})^{x^{2}}')
    def test_existing_valid_latex(self):
        text=r'若 $x^2+\frac{2}{3}=\sqrt{x}$，求值。'
        self.assertEqual(normalize_math_text(text),text)
    def test_unknown_fused_root(self):
        for value in ('aroot(3,a)','asqrt(a)'):
            with self.subTest(value=value),self.assertRaises(FormulaManualReview):normalize_math_text(value)
    def test_unclosed_brace(self): self.assertFalse(validate_math_expression(r'x^{2')['valid'])
    def test_extra_brace(self): self.assertFalse(validate_math_expression(r'x^{2}}')['valid'])
    def test_isolated_dollar(self):
        with self.assertRaises(FormulaManualReview):normalize_math_text('已知 $x=2')
    def test_nested_delimiter(self): self.assertFalse(validate_math_expression('$$x$$')['valid'])
    def test_display_wrapper_removed(self): self.assertEqual(normalize_math_text('$$x^2$$'),'$x^2$')
    def test_alternative_wrapper_removed(self): self.assertEqual(normalize_math_text(r'若 \(x^2\)，求值。'),'若 $x^2$，求值。')
    def test_invalid_frac(self): self.assertFalse(validate_math_expression(r'\frac{2}')['valid'])
    def test_invalid_sqrt(self): self.assertFalse(validate_math_expression(r'\sqrt{}')['valid'])
    def test_missing_exponent_base(self):
        with self.assertRaises(FormulaManualReview):normalize_math_text('0.3^( ^(0.3))')
    def test_log_scope_not_guessed(self):
        with self.assertRaises(FormulaManualReview):normalize_math_text('log_(3)(16)/(9)')
    def test_subjective_all_fields(self):
        for field,value in [('sub_questions',[{'stem':'aroot(3,a)'}]),('reference_answer','aroot(3,a)'),('solution_steps',['aroot(3,a)']),('rubric',[{'criterion':'aroot(3,a)'}]),('reference_answers_by_subquestion',{'1':'aroot(3,a)'})]:
            with self.subTest(field=field):self.assertTrue(audit_question({field:value})['issues'])
    def test_answer_fields(self):
        for field,value in [('canonical_answer','aroot(3,a)'),('accepted_answers',['aroot(3,a)'])]:self.assertTrue(audit_question({field:value})['issues'])
    def test_valid_fill_fraction(self): self.assertTrue(evaluate_fill_blank('0.666666666666666666666','0.666666666666666666666','numeric')); self.assertTrue(evaluate_fill_blank('1/2',r'$\frac{1}{2}$','numeric'))
    def test_valid_fill_expression(self):self.assertTrue(evaluate_fill_blank('(x-1)(x+1)',r'$x^{2}-1$','expression'))
    def test_valid_fill_interval(self):self.assertTrue(evaluate_fill_blank('（-∞，2）',r'$(-\infty ,2)$','interval'))
    def test_valid_fill_set(self):self.assertTrue(evaluate_fill_blank('{2,0.5}',r'$\{1/2,2\}$','set'))
    def test_placeholder_no_crash(self):self.assertEqual(math_markdown(r'$\frac{2}$'),'[公式需要修复]')
    def test_renderer_centralized(self):
        st=MagicMock()
        with patch('services.question_renderer.render_math_text') as render:
            render_answer_input(st,{'question_type':'single_choice','options':dict.fromkeys('ABCD',r'$\frac{2}{3}$')},'answer')
            self.assertEqual(render.call_count,4)
        self.assertNotIn('format_func',st.radio.call_args.kwargs)
    def test_idempotence(self):
        text='若a>0，则a^((2)/(3))+sqrt(a)=2。'
        fixed=normalize_math_text(text);self.assertEqual(normalize_math_text(fixed),fixed)


class FormulaCleanupIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'copy.db'
        with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as src,closing(get_connection(self.path)) as dst:src.backup(dst)
        env=patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2','OPENAI_API_KEY':'','DEEPSEEK_API_KEY':''})
        env.start();self.addCleanup(env.stop)

    def invalid(self,qid='Q001'):
        q=next(q for q in get_approved_questions(include_untrainable=True) if q['id']==qid)
        q['stem']='已知 aroot(3,a)，求函数值。'
        with closing(get_connection()) as c,c:
            c.execute('UPDATE questions SET stem=? WHERE id=?',(q['stem'],qid));store_status(c,q)
        return q

    def test_invalid_not_diagnostic(self):
        q=self.invalid();self.assertNotIn(q['id'],{q['id'] for q in generate_diagnostic_test('FORMULA_NEW')['pool']})
    def test_invalid_not_training(self):
        q=self.invalid();s=start_training_session('FORMULA_NEW',target_knowledge_point_id='K001');selected=get_next_question('FORMULA_NEW',s['id']);self.assertNotEqual(q['id'],selected['id'])
    def test_cached_diagnostic_bad_question_is_skipped(self):
        s=start_diagnostic('FORMULA_NEW');qid=s['current_question']['id'];self.invalid(qid)
        restored=restore_diagnostic('FORMULA_NEW');self.assertNotEqual(restored['current_question']['id'],qid);self.assertEqual(restored['answers'],[])
    def test_training_page_bad_cache_no_crash(self):
        s=start_training_session('S001',target_knowledge_point_id='K001',lock_target=True);q=get_next_question('S001',s['id']);self.invalid(q['id'])
        app=AppTest.from_file(str(ROOT/'app.py')).run();app.switch_page('pages/training.py').run()
        self.assertFalse(app.exception);self.assertNotEqual(app.session_state['adaptive_training_state']['current_question']['id'],q['id'])
    def test_status_explicit_invalid_blocks_even_good_text(self):
        q=self.invalid()
        with closing(get_connection()) as c,c:
            c.execute('UPDATE questions SET stem=? WHERE id=?',('已知函数f(x)=x，求值。',q['id']))
            c.execute('UPDATE question_formula_status SET formula_status=? WHERE question_id=?',('invalid',q['id']))
        self.assertNotIn(q['id'],{q['id'] for q in get_approved_questions()})
    def test_temporary_apply_preserves_all_attempts(self):
        rows=[]
        for q in get_approved_questions(include_untrainable=True):rows.append({'question_id':q['id'],'question_type':q['question_type'],'original_digest':digest(q),**audit_question(q)})
        with closing(get_connection()) as c:before=snapshot(c)
        r=apply(self.path,rows)
        self.assertEqual(before,r['snapshot_after']);self.assertTrue(Path(r['backup']).is_file())
        self.assertTrue(all(q['formula_status']=='valid' and not audit_question(q)['changes'] for q in get_approved_questions()))
    def test_unknown_source_question_quarantined(self):
        q=next(q for q in get_approved_questions(include_untrainable=True) if q['id']=='FM-0c83b8f5a4b3f4cc')
        self.assertEqual(audit_question(q)['formula_status'],'formula_manual_review')
        self.assertNotIn(q['id'],{q['id'] for q in get_approved_questions()})

    def historic_bad_question(self):
        path=ROOT/'data/question_bank/approved/function_multiple_choice_batch_001_approved.jsonl'
        return next(json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if json.loads(s)['id']=='FM-0c83b8f5a4b3f4cc')

    def test_validator_blocks_new_approval_of_unknown_root(self):
        checked=validate_candidate(self.historic_bad_question())
        self.assertFalse(checked['can_approve'])
        self.assertTrue(any('formula_warning' in w for w in checked['warnings']))

    def test_importer_rejects_unknown_formula_without_writes(self):
        with closing(get_connection()) as c:before=snapshot(c)
        with self.assertRaises(ValueError):activate_training_questions([self.historic_bad_question()],database_path=self.path)
        with closing(get_connection()) as c:self.assertEqual(before,snapshot(c))


if __name__=='__main__':unittest.main()
