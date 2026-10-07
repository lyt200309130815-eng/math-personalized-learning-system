"""Recommendation-to-training navigation and the complete approved options chain."""
from contextlib import closing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.database import get_connection, get_approved_questions, record_attempt
from database.taxonomy_migration import migrate_function_v2
from init_db import initialize_database
from scripts.function_v2_dry_run import load_gold
from services.adaptive_training import start_training_session, get_training_session
from services.math_text import math_markdown
from services.recommendation import generate_recommendation

ROOT = Path(__file__).resolve().parents[1]


class RecommendationTrainingIntegrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'integration.db'
        initialize_database(self.path)
        self.gold = load_gold()
        migrate_function_v2(self.path, self.gold)
        env = patch.dict(os.environ, {'MATH_AI_DATABASE_PATH': str(self.path), 'ACTIVE_TAXONOMY_VERSION':'function_v2',
            'OPENAI_API_KEY':'', 'DEEPSEEK_API_KEY':'', 'GEMINI_API_KEY':''})
        env.start()
        self.addCleanup(env.stop)

    def ready(self):
        for key in ('K001','K002','K007','K008','K009','K010'):
            q = get_approved_questions(key)[0]
            for _ in range(6):
                record_attempt('S001', q['id'], q['answer'], 1, 1.)

    def page(self):
        return AppTest.from_file(str(ROOT/'app.py')).run().switch_page('pages/recommendation.py').run()

    def test_all_66_jsonl_options_survive_database_read_boundary(self):
        approved = {q['id']:q for q in get_approved_questions()}
        self.assertEqual(len(self.gold), 66)
        for original in self.gold:
            q = approved[original['id']]
            from services.math_normalizer import normalize_math_text
            self.assertEqual(q['options'], {k:normalize_math_text(v) for k,v in original['options'].items()})
            self.assertEqual(set(q['options']), set('ABCD'))
            self.assertTrue(all(isinstance(value,str) and value.strip() for value in q['options'].values()))
        previews = generate_recommendation('S001')['recommended_questions']
        self.assertTrue(previews)
        self.assertTrue(all('options' not in q and 'answer' not in q for q in previews))

    def test_recommendation_is_preview_only_with_clear_training_entry_and_no_codes(self):
        app = self.page()
        self.assertFalse(app.exception)
        self.assertFalse(app.radio)
        self.assertNotIn('提交答案',[b.label for b in app.button])
        self.assertIn('开始推荐训练',[b.label for b in app.button])
        self.assertTrue(any('进入训练后可正式作答' in c.value for c in app.caption))
        self.assertTrue(all('(K' not in h.value and '（K' not in h.value for h in app.subheader))
        self.assertEqual(len([c for c in app.expander if c.label=='查看一道题干预览']),1)

    def test_recommendation_click_pins_target_then_three_questions_update_once(self):
        self.ready()
        recommendation = generate_recommendation('S001')
        app = self.page()
        next(b for b in app.button if b.label=='开始推荐训练').click().run()
        self.assertFalse(app.exception)
        app.switch_page('pages/training.py').run()  # follow frontend redirect in AppTest
        session_id = app.session_state['adaptive_session_id']
        self.assertEqual(app.session_state['adaptive_training_state']['target_knowledge_point_id'],
                         recommendation['target_knowledge']['knowledge_point_id'])
        chosen = []
        from services.adaptive_training import get_next_question
        with patch('services.adaptive_training.get_next_question', wraps=get_next_question) as selector, \
             patch('services.feedback.generate_text',side_effect=AssertionError('No LLM')):
            for i in range(3):
                state = app.session_state['adaptive_training_state']
                q = state['current_question']
                chosen.append(q['id'])
                self.assertEqual(q['options'], next(p for p in get_approved_questions() if p['id']==q['id'])['options'])
                self.assertEqual(app.radio[0].options, list('ABCD'))
                app.radio[0].set_value(q['answer']).run()
                next(b for b in app.button if b.label=='提交答案').click().run()
                self.assertFalse(app.exception)
                after = get_training_session('S001',session_id)
                self.assertEqual(len(after['answers']),i+1)
                app.run()
                self.assertEqual(len(get_training_session('S001',session_id)['answers']),i+1)
                if i<2:
                    next(b for b in app.button if b.label=='下一题').click().run()
            self.assertGreaterEqual(selector.call_count,2)
        self.assertEqual(len(set(chosen)),3)
        self.assertEqual(get_training_session('S001',session_id)['target_knowledge_point_id'],recommendation['target_knowledge']['knowledge_point_id'])
        with closing(get_connection(read_only=True)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM training_session_questions WHERE session_id=? AND attempt_id IS NOT NULL',(session_id,)).fetchone()[0],3)

    def test_existing_other_target_is_ended_without_losing_answers(self):
        from services.adaptive_training import get_next_question, submit_training_answer
        old = start_training_session('S001',target_knowledge_point_id='K001')
        q = get_next_question('S001',old['id'])
        old = submit_training_answer('S001',old['id'],q['id'],q['answer'],1.)
        self.ready()
        recommendation = generate_recommendation('S001')
        self.assertNotEqual(recommendation['target_knowledge']['knowledge_point_id'],old['target_knowledge_point_id'])
        app = self.page()
        next(b for b in app.button if b.label=='开始推荐训练').click().run()
        app.switch_page('pages/training.py').run()
        new = app.session_state['adaptive_training_state']
        self.assertNotEqual(new['id'],old['id'])
        self.assertEqual(new['target_knowledge_point_id'],recommendation['target_knowledge']['knowledge_point_id'])
        preserved = get_training_session('S001',old['id'])
        self.assertEqual(preserved['status'],'user_ended')
        self.assertEqual(preserved['answers'],old['answers'])

    def test_repeated_recommendation_click_resumes_same_target_session(self):
        self.ready()
        target = generate_recommendation('S001')['target_knowledge']['knowledge_point_id']
        first = start_training_session('S001',target_knowledge_point_id=target,lock_target=True)
        second = start_training_session('S001',target_knowledge_point_id=target,lock_target=True)
        self.assertEqual(first['id'],second['id'])

    def test_changed_prerequisite_cannot_silently_replace_pinned_target(self):
        original = start_training_session('S001')
        with self.assertRaisesRegex(ValueError,'学情已变化'):
            start_training_session('S001',target_knowledge_point_id='K014',lock_target=True)
        self.assertEqual(get_training_session('S001',original['id'])['status'],'active')

    def test_v1_recommendation_still_links_to_legacy_training(self):
        with patch.dict(os.environ,{'ACTIVE_TAXONOMY_VERSION':'function_v1'}):
            app = self.page()
            self.assertFalse(app.exception)
            self.assertFalse(app.radio)
            self.assertFalse(any(b.label=='开始推荐训练' for b in app.button))
            app.switch_page('pages/training.py').run()
            self.assertTrue(app.radio)
            app.radio[0].set_value('D').run()
            app.button[0].click().run()
            self.assertFalse(app.exception)


class MathTextTests(unittest.TestCase):
    def test_requested_simple_power_and_log_examples(self):
        self.assertEqual(math_markdown('已知9^(a)及3^(2a+b)'), '已知$9^{a}$及$3^{2a+b}$')
        self.assertEqual(math_markdown('log_(3)4'), r'$\log_{3} 4$')

    def test_grouped_base_nested_exponent_and_subscript(self):
        self.assertEqual(math_markdown('(x+1)^(a+(b))'), '$(x+1)^{a+(b)}$')
        self.assertEqual(math_markdown('a_(n)^(2)'), '$a_{n}^{2}$')

    def test_roots_and_nested_simple_math(self):
        self.assertEqual(math_markdown('sqrt(x^(2)+1)'), r'$\sqrt{x^{2}+1}$')
        self.assertEqual(math_markdown('root(3,x+1)'), r'$\sqrt[3]{x+1}$')
        self.assertEqual(math_markdown('√(x+1)'), r'$\sqrt{x+1}$')

    def test_plain_chinese_and_existing_latex_preserved(self):
        text = '函数在定义域内单调递增。'
        self.assertEqual(math_markdown(text),text)
        self.assertEqual(math_markdown(r'已知 $x^2$，求值。'),r'已知 $x^2$，求值。')

    def test_unsupported_unbalanced_and_ambiguous_text_remains_literal(self):
        self.assertEqual(math_markdown('9^(a'), '[公式需要修复]')
        self.assertEqual(math_markdown('x^12'), '[公式需要修复]')
        self.assertEqual(math_markdown('root(,x)'), '[公式需要修复]')

    def test_no_evaluation_html_or_markdown_injection(self):
        self.assertEqual(math_markdown('<script>*文字*</script>'),r'\<script\>\*文字\*\</script\>')
