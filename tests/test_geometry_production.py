"""Production curation, isolation and transactional migration on disposable DBs."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from database.database import get_connection, get_approved_questions, get_knowledge_points
from database.geometry import import_geometry
from database.taxonomy_migration import protected_snapshot
from services.geometry_curation import (ROOT, curate_row, real_question_gate, primary_mapping,
                                        strip_answer_leaks, validate_geometry_question)
from geometry_baseline import historical_database
from services.geometry_review import read_rows
from services.question_assets import geometry_trainable, visible_assets
from services.question_renderer import render_question, render_solution
from services.diagnostic import generate_diagnostic_test, start_diagnostic, submit_diagnostic_answer, restore_diagnostic
from services.question_validator import content_fingerprint
from services.adaptive_training import start_training_session, get_next_question, submit_training_answer


def candidate(stem='例1 已知正方体，求体积。', **extra):
    row = {'id': 'TEST-G1', 'stem': stem, 'answer': '答案', 'explanation': '解 体积为1。',
           'reference_solution': '解 体积为1。', 'question_type': 'subjective', 'options': None,
           'source_file': '第七章 §7.1 资料.docx', 'review_asset_ids': [], 'extraction_warnings': [],
           'visual_count_check': {'matches': True}}
    row.update(extra)
    return row


class GeometryGateTests(unittest.TestCase):
    def test_non_question_and_knowledge_summaries_rejected(self):
        for stem in ['1.空间几何体的结构特征', '基本事实1……基本事实4……', '异面直线所成的角：cosθ=1/2',
                     '直线和平面所成角的定义', '定理：直线平行于平面', '性质：共面向量', '公式总结：V=Sh']:
            with self.subTest(stem=stem):
                self.assertFalse(real_question_gate(candidate(stem))[0])
                self.assertEqual(curate_row(candidate(stem), {})['decision'], 'rejected_non_question')

    def test_judgment_leak_stripped_to_structured_answers(self):
        stem = '判断下列结论是否正确\n(1)结论一（√）\n(2)结论二( × )'
        text, answers, events, status = strip_answer_leaks(stem)
        self.assertNotIn('（√）', text)
        self.assertNotIn('( × )', text)
        self.assertEqual(answers, {'1': '√', '2': '×'})
        self.assertEqual(status, 'clean')
        self.assertEqual(len(events), 2)

    def test_ambiguous_leak_blocked(self):
        for stem in ['求体积，故选A', '求面积\n解析 因此答案A', '判断是否正确\n(1)结论（√）\n(2)结论']:
            self.assertEqual(strip_answer_leaks(stem)[3], 'needs_manual_fix')

    def test_source_chapter_mapping_and_g009(self):
        for chapter in range(1, 11):
            row = candidate('求正方体截面', source_file=f'第七章 §7.{chapter} 资料.docx')
            self.assertEqual(primary_mapping(row)[0], f'G{chapter:03}')
        self.assertEqual(primary_mapping(candidate('作出点线面形成的截面', source_file='第七章 §7.9 资料.docx'))[0], 'G009')

    def test_default_no_diagram_and_explicit_diagram_block(self):
        row = curate_row(candidate(), {})
        self.assertFalse(row['diagram_required'])
        row = curate_row(candidate('例1 如图求体积'), {})
        self.assertTrue(row['diagram_required'])
        self.assertIn('missing_required_diagram', row['issues'])
        self.assertFalse(row['trainable'])

    def test_option_image_requires_diagram_and_solution_is_hidden(self):
        row = {'real_question': True, 'quality_status': 'approved', 'formula_status': 'valid',
               'answer_leak_status': 'clean', 'structure_status': 'valid', 'diagram_required': True,
               'diagram_assets': [{'role': 'option_image', 'path': 'missing.png'}, {'role': 'solution_diagram', 'path': 'solution.png'}]}
        self.assertTrue(geometry_trainable(row, check_files=False))
        self.assertFalse(geometry_trainable(row))
        self.assertEqual([a['role'] for a in visible_assets(row)], ['option_image'])
        self.assertEqual([a['role'] for a in visible_assets(row, solution=True)], ['solution_diagram'])
        st = MagicMock()
        render_solution(st, row, submitted=False)
        st.image.assert_not_called()
        st.subheader.assert_not_called()

    def test_runtime_missing_diagram_returns_false_without_crash(self):
        st = MagicMock()
        self.assertFalse(render_question(st, {'id': 'bad', 'stem': '如图求体积', 'diagram_required': True, 'diagram_assets': []}))
        st.image.assert_not_called()

    def test_unresolved_formula_never_approved(self):
        row = curate_row(candidate(stem='例1 求[公式待核]的值', extraction_warnings=['包含无法可靠转换的 OMML 公式']), {})
        self.assertEqual(row['decision'], 'needs_manual_fix')
        self.assertFalse(row['trainable'])

    def test_actual_pool_all_gate_conditions_and_no_markers(self):
        rows = read_rows(ROOT / 'data/question_bank/geometry_v1_1c/approved_ready.jsonl')
        for row in rows:
            self.assertTrue(geometry_trainable(row, check_files=False), row['id'])
            self.assertFalse(validate_geometry_question(row), row['id'])
            self.assertFalse(row['issues'])
            self.assertFalse(row.get('warnings'))
            for field in ['stem', 'options', 'explanation', 'canonical_answer', 'reference_answer', 'sub_questions']:
                text = str(row.get(field, ''))
                self.assertNotIn('[公式待核]', text)
                self.assertNotIn('[图片待核]', text)
                self.assertNotIn('sqrt(', text)


class GeometryMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'geometry.sqlite3'
        with closing(get_connection(historical_database(), read_only=True)) as original, closing(get_connection(cls.path)) as target:
            original.backup(target)
        cls.rows = read_rows(ROOT / 'data/question_bank/geometry_v1_1c/approved_ready.jsonl')
        with closing(get_connection(cls.path, read_only=True)) as connection:
            cls.before = protected_snapshot(connection)
        cls.function_before = get_approved_questions(database_path=cls.path, taxonomy_version='function_v2')
        cls.result = import_geometry(cls.path, cls.rows)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_attempts_digest_unchanged(self):
        with closing(get_connection(self.path, read_only=True)) as connection:
            after = protected_snapshot(connection)
        # Diagnostic/training tests in this class use different cloned DBs.
        self.assertEqual(self.before['attempts_digest'], after['attempts_digest'])

    def test_migration_idempotent_and_function_isolated(self):
        again = import_geometry(self.path, self.rows)
        self.assertEqual(again['inserted'], 0)
        self.assertEqual(again['skipped'], len(self.rows))
        self.assertEqual(get_approved_questions(database_path=self.path, taxonomy_version='function_v2'), self.function_before)
        self.assertEqual(len(get_knowledge_points('geometry_v1', database_path=self.path)), 10)
        self.assertEqual(len(get_approved_questions(database_path=self.path, taxonomy_version='geometry_v1')), len(self.rows))

    def clone(self, name):
        path = Path(self.temp.name) / name
        with closing(get_connection(self.path, read_only=True)) as original, closing(get_connection(path)) as target:
            original.backup(target)
        return path

    def test_diagnosis_uses_geometry_only_and_ten_submissions(self):
        path = self.clone('diagnosis.db')
        state = start_diagnostic('GEOMETRY-TEST', taxonomy_version='geometry_v1', database_path=path)
        self.assertEqual(state['max_questions'], 15)
        self.assertTrue(all(q['taxonomy_version'] == 'geometry_v1' for q in state['pool']))
        self.assertGreaterEqual(len({q['knowledge_point_id'] for q in state['pool']}), 9)
        for _ in range(10):
            q = state['current_question']
            value = q.get('answer') or json.dumps(q.get('correct_answers')) if q['question_type'] in ('single_choice', 'multiple_choice') else q.get('canonical_answer') or '已写出证明过程。'
            state = submit_diagnostic_answer(state['id'], q['id'], value, database_path=path, answer_time=1)
        self.assertEqual(len(state['answers']), 10)
        function = start_diagnostic('GEOMETRY-TEST', taxonomy_version='function_v2', database_path=path)
        self.assertNotEqual(function['id'], state['id'])
        self.assertTrue(all(not q['knowledge_point_id'].startswith('G') for q in function['pool']))
        self.assertEqual(restore_diagnostic('GEOMETRY-TEST', taxonomy_version='geometry_v1', database_path=path)['id'], state['id'])

    def test_geometry_adaptive_session_selects_and_submits_geometry(self):
        path = self.clone('adaptive.db')
        state = start_training_session('G-ADAPTIVE', taxonomy_version='geometry_v1', target_knowledge_point_id='G001', database_path=path)
        q = get_next_question('G-ADAPTIVE', state['id'], database_path=path)
        self.assertIsNotNone(q)
        self.assertEqual(q['taxonomy_version'], 'geometry_v1')
        value = q.get('answer') or q.get('canonical_answer') or json.dumps(q.get('correct_answers'))
        result = submit_training_answer('G-ADAPTIVE', state['id'], q['id'], value, 1, database_path=path)
        self.assertTrue(result['submitted'])

    def test_missing_required_images_are_skipped_in_diagnostic_pool(self):
        with patch('services.question_assets.readable_asset', return_value=False):
            state = generate_diagnostic_test('BROKEN-IMAGE', taxonomy_version='geometry_v1', database_path=self.path)
        self.assertTrue(state['pool'])
        self.assertTrue(all(not q['diagram_required'] for q in state['pool']))

    def test_batch_failure_rolls_back(self):
        path = self.clone('rollback.db')
        rows = deepcopy(self.rows[:1])
        rows[0]['id'] = 'COLLISION-GEOMETRY'
        rows[0]['stem'] += '（独立回滚测试题）'
        rows[0]['fingerprint'] = content_fingerprint(rows[0])
        with closing(get_connection(path)) as connection, connection:
            connection.execute("INSERT INTO questions SELECT 'COLLISION-GEOMETRY',stem,options,answer,explanation,knowledge_point_id,difficulty,ability_tag,question_type,estimated_time FROM questions WHERE id=?", (self.rows[0]['id'],))
        before = path.read_bytes()
        with self.assertRaises(Exception):
            import_geometry(path, rows)
        self.assertEqual(path.read_bytes(), before)
