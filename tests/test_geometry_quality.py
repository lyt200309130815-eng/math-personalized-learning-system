"""V1.1D source recovery, coverage and geometry quality on disposable databases."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from streamlit.testing.v1 import AppTest

from database.database import get_approved_questions, get_connection, record_attempt
from services.adaptive_training import (exposure_tokens, get_next_question, get_training_session,
                                       start_training_session, submit_training_answer)
from services.diagnostic import generate_diagnostic_test, explain_profile
from services.geometry_curation import curate_row
from services.geometry_quality import classify_geometry_difficulty, geometry_difficulty_range, source_fingerprint
from services.geometry_recovery import production_audit, SOLUTION_START
from geometry_baseline import historical_database
from services.geometry_review import ROOT, read_rows, verify_docx, ReviewDocx
from services.mastery import calculate_knowledge_mastery
from services.math_normalizer import audit_question, validate_math_expression
from services.profile import build_profile_data
from services.question_assets import visible_assets, geometry_trainable
from services.question_renderer import render_question, render_solution
from services.question_validator import content_fingerprint
from services.recommendation import generate_recommendation
from services.source_extractors.docx_question_extractor import M, W, _math
from services.source_extractors.geometry_math import geometry_math, normalize_geometry_text

BANK = ROOT / 'data/question_bank/geometry_v1_1d'


class GeometryRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recovered = read_rows(BANK / 'geometry_recovery_batch_001.jsonl')
        cls.analysis = read_rows(BANK / 'recovery_analysis.jsonl')
        cls.details = read_rows(BANK / 'recovery_question_details.jsonl')
        cls.summary = json.loads((BANK / 'recovery_summary.json').read_text(encoding='utf-8'))

    def test_coverage_matches_direct_production_sql(self):
        audit, rows = production_audit(historical_database())
        with closing(get_connection(historical_database(), read_only=True)) as conn:
            counts = dict(conn.execute("SELECT knowledge_point_id,COUNT(*) FROM question_knowledge_mappings WHERE taxonomy_version='geometry_v1' AND role='primary' AND review_status='approved' GROUP BY knowledge_point_id"))
            levels = dict(conn.execute("SELECT q.difficulty,COUNT(*) FROM questions q JOIN question_knowledge_mappings m ON m.question_id=q.id WHERE m.taxonomy_version='geometry_v1' AND m.role='primary' AND m.review_status='approved' GROUP BY q.difficulty"))
        self.assertEqual(counts, {k: p['count'] for k, p in audit['points'].items()})
        self.assertEqual(levels, audit['difficulty'])
        self.assertEqual(audit['database_counts']['questions'], 256)
        self.assertGreaterEqual(audit['database_counts']['attempts'], 79)
        self.assertEqual(len(rows), 123)
        self.assertEqual(audit['difficulty'], {2: 109, 3: 14})
        self.assertEqual(audit['types'], dict(single_choice=60, multiple_choice=23, fill_blank=26, subjective=14))

    def test_g008_gap_is_not_inflated_by_chapter_only_tasks(self):
        audit, _ = production_audit(historical_database())
        self.assertEqual(audit['points']['G008']['gap_to_10'], 9)
        recovered = [q for q in self.recovered if q['primary_knowledge_point_id'] == 'G008']
        self.assertEqual(len(recovered), 7)
        for q in recovered:
            task = q['stem'] + '\n'.join((q.get('options') or {}).values()) + '\n'.join(s['stem'] for s in q.get('sub_questions', []))
            self.assertIn('距离', task)
        self.assertEqual(1 + len(recovered), 8)

    def test_only_original_99_pending_records_are_processed(self):
        prior = read_rows(ROOT / 'data/question_bank/geometry_v1_1c/curated_candidates.jsonl')
        ids = {q['id'] for q in prior if q['decision'] == 'needs_manual_fix'}
        self.assertEqual(len(ids), 99)
        self.assertEqual({q['id'] for q in self.analysis}, ids)
        self.assertTrue(all(q['source_parent_id'] in ids for q in self.recovered))
        self.assertEqual(len(self.recovered), self.summary['recovered'])
        self.assertEqual(sum(self.summary['points'].values()), len(self.recovered))
        self.assertEqual(sum(self.summary['classes'].values()), 99)

    def test_ambiguous_source_font_glyph_is_not_guessed(self):
        q = next(q for q in self.details if q['id'] == 'GQ-50a2466ead939ff28bd5')
        self.assertFalse(q['recovery_ready'])
        self.assertEqual(q['recovery_class'], 'still_ambiguous')
        self.assertIn('formula_warning', q['issues'])
        self.assertTrue(any('GBK_S' in warning for warning in q['extraction_warnings']))
        self.assertNotIn(q['id'], {q['id'] for q in self.recovered})

    def test_source_splits_have_disjoint_ranges_and_traceable_parent(self):
        groups = {}
        for q in self.recovered:
            groups.setdefault(q['source_parent_id'], []).append(q)
        for rows in groups.values():
            rows.sort(key=lambda q: q['start_paragraph'])
            for left, right in zip(rows, rows[1:]):
                self.assertLess(left['end_paragraph'], right['start_paragraph'])
        self.assertGreater(len(self.recovered), len(self.analysis))

    def test_reviewed_does_not_mean_approved_or_trainable(self):
        for q in self.recovered:
            self.assertEqual(q['quality_status'], 'reviewed')
            self.assertEqual(q['review_status'], 'pending_review')
            self.assertEqual(q['decision'], 'pending_review')
            self.assertFalse(q['trainable'])
            self.assertFalse(geometry_trainable(q, check_files=False))
            self.assertFalse(q['issues'], q['id'])

    def test_recovered_not_duplicate_of_current_approved(self):
        approved = get_approved_questions(database_path=historical_database(), taxonomy_version='geometry_v1')
        existing_content = {content_fingerprint(q) for q in approved}
        existing_source = {source_fingerprint(q) for q in approved}
        self.assertTrue({q['fingerprint'] for q in self.recovered}.isdisjoint(existing_content))
        self.assertTrue({q['source_fingerprint'] for q in self.recovered}.isdisjoint(existing_source))
        self.assertEqual(len({q['source_fingerprint'] for q in self.recovered}), len(self.recovered))

    def test_all_recovered_formulas_are_valid_on_repeated_audit(self):
        for q in self.recovered:
            self.assertEqual(q['formula_status'], 'valid')
            result = audit_question(q)
            self.assertFalse(result['issues'], (q['id'], result['issues']))
            self.assertEqual(result['normalized'], q)
            self.assertNotIn('[公式待核]', str(q.get('sub_questions', [])))

    def test_source_assets_are_intact_and_solution_roles_do_not_leak(self):
        for q in self.recovered:
            if q['diagram_required']:
                self.assertTrue(visible_assets(q), q['id'])
            for a in q['diagram_assets']:
                path = ROOT / 'data/question_bank/geometry_v1_1a' / a['source_path']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), a['source_sha256'])
                field = q['paragraph_fields'][str(int(a['source_locator'].split('paragraph ')[1].split()[0]))]
                if field == 'explanation':
                    self.assertEqual(a['role'], 'solution_diagram')
                self.assertTrue(a['role'] in ('question_diagram', 'option_image', 'solution_diagram'))
            self.assertTrue(all(a['role'] != 'solution_diagram' for a in visible_assets(q)))

    def test_renderer_pre_answer_and_post_answer_images(self):
        q = next(q for q in self.recovered if visible_assets(q) and visible_assets(q, solution=True))
        st = MagicMock()
        with patch('services.question_renderer.render_math_text'), patch('services.question_assets.readable_asset', return_value=True), patch('services.question_renderer.readable_asset', return_value=True), patch('services.question_renderer.asset_path', return_value=ROOT / 'tmp/test.png'):
            self.assertTrue(render_question(st, q))
            self.assertEqual(st.image.call_count, len(visible_assets(q)))
            st.reset_mock()
            render_solution(st, q, submitted=False)
            st.image.assert_not_called()
            render_solution(st, q, submitted=True)
            self.assertEqual(st.image.call_count, len(visible_assets(q, solution=True)))

    def test_review_word_has_only_recovered_questions_and_embedded_math(self):
        word = ROOT / 'reports/geometry_recovery_batch_001_可读版.docx'
        verified = verify_docx(word)
        self.assertEqual(verified['embedded_images'], sum(len(q['diagram_assets']) for q in self.recovered))
        self.assertGreater(verified['native_math_count'], 0)
        with ZipFile(word) as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        self.assertTrue(all(q['id'] in xml for q in self.recovered))
        self.assertTrue(all(q['id'] not in xml for q in self.details if q['recovery_class'] == 'non_question'))

    def test_twelve_sources_scanned_and_production_bytes_unchanged(self):
        scans = json.loads((BANK / 'source_scan.json').read_text(encoding='utf-8'))
        self.assertEqual(len(scans), 12)
        self.assertEqual(self.summary['production_sha256_before'], self.summary['production_sha256_after'])
        self.assertFalse(self.summary['production_db_modified'])
        # The live app may collect real practice while we work. Recovery's own
        # paired read-only snapshots must agree; never delete later student data.


class GeometryMathTests(unittest.TestCase):
    def parse(self, inner):
        return ET.fromstring(f'<m:oMath xmlns:m="{M[1:-1]}">{inner}</m:oMath>')

    def test_vector_arrow_is_recovered_from_exact_accent(self):
        node = self.parse('<m:acc><m:accPr><m:chr m:val="⃗"/></m:accPr><m:e><m:r><m:t>AB</m:t></m:r></m:e></m:acc>')
        self.assertEqual(geometry_math(node), r'$\overrightarrow{AB}$')
        with self.assertRaises(ValueError):
            _math(node)

    def test_fraction_and_matrix_keep_every_source_cell(self):
        node = self.parse('<m:m><m:mr><m:e><m:r><m:t>x=1</m:t></m:r></m:e></m:mr><m:mr><m:e><m:r><m:t>y=2</m:t></m:r></m:e></m:mr></m:m>')
        value = geometry_math(node)
        self.assertIn('x=1', value)
        self.assertIn('y=2', value)
        self.assertIn(r'\\', value)
        self.assertTrue(validate_math_expression(value[1:-1])['valid'])

    def test_unknown_and_incomplete_formula_are_blocked(self):
        for source in ['<m:unknown/>', '<m:f><m:num><m:r><m:t>1</m:t></m:r></m:num></m:f>',
                       '<m:sSup><m:e/><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>',
                       '<m:rad><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>',
                       '<m:m><m:mr><m:e/></m:mr></m:m>']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                geometry_math(self.parse(source))

    def test_numbered_proof_task_is_not_a_solution_heading(self):
        self.assertFalse(SOLUTION_START.match('(1)证明：平面甲⊥平面乙；'))
        self.assertTrue(SOLUTION_START.match('(1)证明　因为AB⊥CD，'))
        self.assertTrue(SOLUTION_START.match('(2)解　建立坐标系'))

    def test_review_source_keeps_word_styled_superscripts(self):
        node = ET.fromstring(f'<w:p xmlns:w="{W[1:-1]}"><w:r><w:t>AB</w:t></w:r><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>2</w:t></w:r></w:p>')
        doc = ReviewDocx('source scripts')
        doc.native_source(node, preserve_scripts=True)
        self.assertEqual(doc.body.find('.//' + W + 'vertAlign').get(W + 'val'), 'superscript')

    def test_adjacent_math_and_option_labels_keep_valid_delimiters(self):
        value = normalize_geometry_text('A.Ω_(1)的体积为$\\frac{1}{2}$ B.AB_(1)⊥平面ABC')
        self.assertTrue(value.startswith('A. '))
        self.assertIn(' B. ', value)
        self.assertEqual(value.count('$') % 2, 0)
        for marker in ('（√）', '( × )'):
            self.assertIn(marker, normalize_geometry_text('判断结论' + marker))


class GeometryDifficultyTests(unittest.TestCase):
    def classify(self, stem, solution='', **extra):
        return classify_geometry_difficulty(dict(stem=stem, explanation=solution, **extra))['suggested']

    def test_definition_is_d1_and_routine_calculation_d2(self):
        self.assertEqual(self.classify('判断基本定义是否正确。'), 1)
        self.assertEqual(self.classify('求正方体的体积。', '由V=a³代入得8。'), 2)

    def test_vector_calculation_and_general_proof_are_d3(self):
        self.assertEqual(self.classify('求向量数量积。', '建立空间直角坐标系，计算坐标。'), 3)
        self.assertEqual(self.classify('证明平面甲平行平面乙。', '所以直线平行，因此平面平行。'), 3)

    def test_combined_distance_with_source_steps_is_d4(self):
        self.assertEqual(self.classify('求点到平面的距离。', '建立空间直角坐标系，所以坐标已知，设平面法向量，解得法向量，因此代入距离公式。'), 4)

    def test_dynamic_multichain_exploration_is_d5(self):
        self.assertEqual(self.classify('证明垂直；是否存在动点，使距离满足条件并求轨迹。', '所以' * 7), 5)
        self.assertLess(self.classify('动点运动，求长度。', '所以代入得到1。'), 5)

    def test_question_type_does_not_mechanically_set_difficulty(self):
        for kind in ('single_choice', 'multiple_choice', 'fill_blank', 'subjective'):
            self.assertEqual(self.classify('计算体积。', '代入V=Sh。', question_type=kind), 2)

    def test_geometry_bands_use_mastery_and_independent_evidence(self):
        for score, count, expected in [(None,0,(1,2)), (.2,6,(1,2)), (.65,6,(2,3)), (.85,6,(3,4)), (.95,6,(4,5)), (.99,2,(1,2))]:
            self.assertEqual(geometry_difficulty_range(dict(mastery_score=score, attempt_count=count)), expected)
        self.assertEqual(geometry_difficulty_range(dict(mastery_score=1, attempt_count=20, source_evidence_count=1)), (1,2))

    def test_source_fingerprint_survives_text_repair_but_not_a_new_origin(self):
        q = dict(id='first', source_file='source.docx', source_locator='word/document.xml paragraphs 10–20', stem='原文')
        repaired = dict(q, id='second', stem='恢复公式', source_locator='word/document.xml paragraphs 10–19')
        self.assertEqual(source_fingerprint(q), source_fingerprint(repaired))
        self.assertNotEqual(source_fingerprint(q), source_fingerprint(dict(q, source_locator='word/document.xml paragraphs 30–40')))

    def test_identical_content_in_another_source_remains_the_same_exposure(self):
        q = dict(id='first', taxonomy_version='geometry_v1', stem='求体积。', options={'A':'1','B':'2'}, answer='A', source_file='source1.docx', source_locator='word/document.xml paragraphs 10–20')
        other = dict(q, id='second', source_file='source2.docx', source_locator='word/document.xml paragraphs 100–110')
        self.assertNotEqual(source_fingerprint(q), source_fingerprint(other))
        self.assertTrue(exposure_tokens(q) & exposure_tokens(other))


class GeometryAdaptiveQualityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'geometry_quality.db'
        with closing(get_connection(historical_database(), read_only=True)) as src, closing(get_connection(self.path)) as dst:
            src.backup(dst)
        self.student = 'V1_1D_TEST'
        self.function_before = get_approved_questions(database_path=self.path, taxonomy_version='function_v2')

    def mastery(self, key='G001'):
        return calculate_knowledge_mastery(self.student, key, database_path=self.path, taxonomy_version='geometry_v1')

    def seed(self, values):
        pool = [q for q in get_approved_questions('G001', database_path=self.path, taxonomy_version='geometry_v1') if q['question_type'] != 'subjective']
        for q, correct in zip(pool, values):
            answer = q['answer'] if q['question_type'] == 'single_choice' else q.get('canonical_answer') or json.dumps(q.get('correct_answers'))
            if not correct:
                answer = next(c for c in 'ABCD' if c != q['answer']) if q['question_type'] == 'single_choice' else 'wrong'
            record_attempt(self.student, q['id'], answer, correct, 2, database_path=self.path, taxonomy_version='geometry_v1')

    def fixture_questions(self, levels, same_source=False):
        base = next(q for q in get_approved_questions('G001', database_path=self.path, taxonomy_version='geometry_v1') if q['question_type'] == 'single_choice' and not q['diagram_required'])
        with closing(get_connection(self.path)) as conn, conn:
            for i, level in enumerate(levels):
                qid = f'QUALITY_D{level}_{i}'
                conn.execute('INSERT INTO questions SELECT ?,stem,options,answer,explanation,knowledge_point_id,?,ability_tag,question_type,estimated_time FROM questions WHERE id=?', (qid, level, base['id']))
                conn.execute('UPDATE questions SET stem=stem||? WHERE id=?', (f'（离线独立测试题{level}-{i}）',qid))
                conn.execute('INSERT INTO question_knowledge_mappings VALUES (?,?,?,?,?)', ('geometry_v1', qid, 'G001', 'primary', 'approved'))
                conn.execute('INSERT INTO question_type_extensions SELECT ?,payload FROM question_type_extensions WHERE question_id=?', (qid, base['id']))
                start = 1000 if same_source else 1000 + i*10
                conn.execute('INSERT INTO question_sources VALUES (?,?,?,?,?,?,?,?,?)', ('fixture:'+qid,qid,'geometry_v1','docx','quality_fixture.docx',f'word/document.xml paragraphs {start}–{start+2}','1','approved',qid))
        return [q for q in get_approved_questions('G001', database_path=self.path, taxonomy_version='geometry_v1') if q['id'].startswith('QUALITY_')]

    def session(self):
        return start_training_session(self.student, taxonomy_version='geometry_v1', target_knowledge_point_id='G001', database_path=self.path)

    def test_untrained_low_mid_high_and_stable_progression(self):
        for index, (values, expected) in enumerate([((),1), ((0,0,0,0,0,0),1), ((1,1,1,1,0,0),2), ((0,1,1,1,1,1),3), ((1,1,1,1,1,1),4)]):
            self.student = f'V1_1D_BAND_{index}'
            self.seed(values)
            fixtures = self.fixture_questions(range(1,6)) if index == 0 else [q for q in get_approved_questions('G001', database_path=self.path,taxonomy_version='geometry_v1') if q['id'].startswith('QUALITY_')]
            state = self.session()
            with patch('services.adaptive_training._eligible', return_value=fixtures):
                q = get_next_question(self.student, state['id'], database_path=self.path)
            self.assertEqual(q['difficulty'], expected)

    def test_stable_student_can_reach_d5_after_a_correct_pair(self):
        self.seed((1,1,1,1,1,1))
        fixtures = self.fixture_questions((4,4,5))
        state = self.session()
        with patch('services.adaptive_training._eligible', return_value=fixtures):
            for _ in range(2):
                q = get_next_question(self.student, state['id'], database_path=self.path)
                self.assertEqual(q['difficulty'], 4)
                submit_training_answer(self.student, state['id'], q['id'], q['answer'], 2, database_path=self.path)
            q = get_next_question(self.student, state['id'], database_path=self.path)
        self.assertEqual(q['difficulty'], 5)

    def test_missing_advanced_difficulty_is_explicit_not_d2_fallback(self):
        self.seed((1,1,1,1,1,1))
        fixtures = self.fixture_questions((2,))
        state = self.session()
        with patch('services.adaptive_training._eligible', return_value=fixtures):
            self.assertIsNone(get_next_question(self.student, state['id'], database_path=self.path))
        stored = get_training_session(self.student, state['id'], database_path=self.path)
        self.assertEqual(stored['status'], 'coverage_limited')
        self.assertIn('D4/D5', stored['difficulty_coverage_limitation'][0])

    def test_high_mastery_uses_d3_with_d4_limitation(self):
        self.seed((0,1,1,1,1,1))
        fixtures = self.fixture_questions((3,))
        state = self.session()
        with patch('services.adaptive_training._eligible', return_value=fixtures):
            q = get_next_question(self.student, state['id'], database_path=self.path)
        self.assertEqual(q['difficulty'], 3)
        self.assertIn('D4', get_training_session(self.student,state['id'],database_path=self.path)['difficulty_coverage_limitation'][0])

    def test_low_mastery_cannot_receive_an_advanced_fixture(self):
        fixtures = self.fixture_questions((4,5))
        state = self.session()
        with patch('services.adaptive_training._eligible', return_value=fixtures):
            self.assertIsNone(get_next_question(self.student, state['id'], database_path=self.path))

    def test_same_source_alias_not_repeated_within_session(self):
        self.seed((1,1,1,1,1,1))
        fixtures = self.fixture_questions((4,5), same_source=True)
        state = self.session()
        with patch('services.adaptive_training._eligible', return_value=fixtures):
            q = get_next_question(self.student, state['id'], database_path=self.path)
            submit_training_answer(self.student, state['id'], q['id'], q['answer'], 2, database_path=self.path)
            self.assertIsNone(get_next_question(self.student, state['id'], database_path=self.path))
        self.assertTrue(exposure_tokens(fixtures[0]) & exposure_tokens(fixtures[1]))

    def test_unanswered_rerun_returns_same_question(self):
        state = self.session()
        q = get_next_question(self.student, state['id'], database_path=self.path)
        self.assertEqual(get_next_question(self.student, state['id'], database_path=self.path)['id'], q['id'])

    def test_recent_g008_is_not_repeated_in_diagnostic(self):
        q = get_approved_questions('G008', database_path=self.path, taxonomy_version='geometry_v1')[0]
        record_attempt(self.student, q['id'], 'fixture', 0, 2, database_path=self.path, taxonomy_version='geometry_v1')
        state = generate_diagnostic_test(self.student, 'geometry_v1', database_path=self.path)
        self.assertTrue(all(q['knowledge_point_id'] != 'G008' for q in state['pool']))
        self.assertTrue(any('G008' in note and '不重复' in note for note in state['coverage_limitations']))
        mastery = self.mastery('G008')
        self.assertEqual(mastery['mastery_score'], 0)
        self.assertEqual(mastery['mastery_display'], '证据不足 / 待进一步训练')
        self.assertEqual(build_profile_data([mastery])['chart'], [])
        self.assertTrue(explain_profile([mastery])['证据不足知识点'])

    def test_diagnostic_covers_ten_points_in_fifteen_unique_questions(self):
        state = generate_diagnostic_test(self.student, 'geometry_v1', database_path=self.path)
        selected = [q for q in state['pool'] if q['id'] in state['planned_question_ids']]
        self.assertEqual(len(selected), 15)
        self.assertEqual(len({q['knowledge_point_id'] for q in selected}), 10)
        self.assertEqual(len({q['source_fingerprint'] for q in selected}), 15)

    def test_diagnostic_and_training_do_not_affect_function_pool_or_s001(self):
        with closing(get_connection(self.path, read_only=True)) as conn:
            before = [tuple(r) for r in conn.execute("SELECT * FROM attempts WHERE student_id='S001' ORDER BY id")]
        state = self.session()
        q = get_next_question(self.student, state['id'], database_path=self.path)
        submit_training_answer(self.student,state['id'],q['id'],q['answer'] or q.get('canonical_answer') or json.dumps(q.get('correct_answers')),2,database_path=self.path)
        generate_diagnostic_test(self.student,'geometry_v1',database_path=self.path)
        self.assertEqual(get_approved_questions(database_path=self.path,taxonomy_version='function_v2'),self.function_before)
        with closing(get_connection(self.path, read_only=True)) as conn:
            self.assertEqual([tuple(r) for r in conn.execute("SELECT * FROM attempts WHERE student_id='S001' ORDER BY id")], before)

    def test_recommendation_does_not_choose_the_largest_pool(self):
        rec = generate_recommendation(self.student, database_path=self.path, taxonomy_version='geometry_v1')
        self.assertEqual(rec['target_knowledge']['knowledge_point_id'], 'G001')
        self.assertTrue(any('D1' in note for note in rec['coverage_limitations']))

    def test_actual_profile_page_keeps_sparse_geometry_evidence_explicit(self):
        q = get_approved_questions('G008', database_path=self.path, taxonomy_version='geometry_v1')[0]
        answer = next(c for c in 'ABCD' if c != q['answer']) if q['question_type'] == 'single_choice' else 'wrong'
        record_attempt(self.student,q['id'],answer,0,2,database_path=self.path,taxonomy_version='geometry_v1')
        with patch.dict(os.environ, {'MATH_AI_DATABASE_PATH':str(self.path), 'ACTIVE_TAXONOMY_VERSION':'geometry_v1'}):
            app = AppTest.from_file(str(ROOT/'app.py'))
            app.session_state['student_id'] = self.student
            app.run().switch_page('pages/profile.py').run()
            self.assertFalse(app.exception)
            text = '\n'.join(m.value for m in app.markdown)
            self.assertIn('证据不足 / 待进一步训练', text)
            self.assertNotIn('掌握度：0%', text)

    def test_actual_training_page_shows_difficulty_coverage_limits(self):
        with patch.dict(os.environ, {'MATH_AI_DATABASE_PATH':str(self.path), 'ACTIVE_TAXONOMY_VERSION':'geometry_v1'}):
            app = AppTest.from_file(str(ROOT/'app.py'))
            app.session_state['student_id'] = self.student
            app.run().switch_page('pages/training.py').run()
            next(b for b in app.button if b.label=='开始个性化训练').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('coverage limitation' in item.value for item in app.info))

    def test_unsafe_formula_marker_remains_withheld_in_review_mode(self):
        candidate = dict(id='UNSAFE', stem='例1 求[公式待核]的值。', answer='A',
                         options=dict(A='1',B='2',C='3',D='4'), explanation='无法确定缺失内容。',
                         reference_solution='无法确定缺失内容。', question_type='single_choice',
                         source_file='第七章 §7.8 资料.docx', review_asset_ids=[],
                         extraction_warnings=['包含无法可靠转换的 OMML 公式'], visual_count_check={'matches':True})
        row = curate_row(candidate, {}, review_only=True)
        self.assertEqual(row['decision'],'needs_manual_fix')
        self.assertNotEqual(row['formula_status'],'valid')
        self.assertFalse(row['trainable'])


if __name__ == '__main__':
    unittest.main()
