"""Offline review-pack invariants; no production database fixtures."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from PIL import Image

from services.geometry_review import (A, M, R, W, WP, ReviewDocx, add_assets,
                                     add_question, classify_assets, initialize_decisions,
                                     knowledge_suggestion, prepare_questions,
                                     read_rows, verify_docx)


class GeometryReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / '原始.docx'
        with ZipFile(self.source, 'w') as archive:
            for number in range(1, 4):
                buffer = io.BytesIO()
                Image.new('RGB', (600, 300), ('red', 'blue', 'green')[number - 1]).save(buffer, format='PNG')
                archive.writestr(f'word/media/image{number}.png', buffer.getvalue())
        self.questions = [{'id': 'Q1', 'source_file': str(self.source), 'source_sha256': self.digest(self.source),
                           'source_question_number': '例1', 'source_locator': 'paragraphs 1-4',
                           'start_paragraph': 1, 'end_paragraph': 4, 'stem': '例1 如图求体积\nA.1 B.2 C.3 D.4',
                           'answer': '答案 A', 'explanation': '解析 体积为1', 'asset_ids': ['I1', 'I2'],
                           'extraction_warnings': [], 'quality_status': 'draft'}]
        self.assets = []
        for number, role, qid in [(1, 'stem', 'Q1'), (2, 'explanation', 'Q1'), (3, 'unassigned', None)]:
            path = self.root / f'image{number}.png'
            Image.new('RGB', (600, 300), ('red', 'blue', 'green')[number - 1]).save(path)
            self.assets.append({'id': f'I{number}', 'question_id': qid, 'source_file': str(self.source),
                                'source_sha256': self.digest(self.source), 'source_locator': f'word/document.xml paragraph {number+1} visual 1',
                                'role': role, 'resources': [{'path': path.name, 'sha256': self.digest(path),
                                                          'package_part': f'word/media/image{number}.png'}]})
        self.blocks = {str(self.source): [{'index': i, 'text': text, 'warnings': []}
                                        for i, text in enumerate(['例1 如图求体积', '[图片待核]', '解析 [图片待核]', '思维升华'], 1)]}

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def prepared(self):
        assets = classify_assets(self.questions, self.assets, self.root, self.blocks)
        return prepare_questions(self.questions, assets, self.blocks), assets

    def test_images_embedded_in_order_with_preserved_aspect(self):
        questions, assets = self.prepared()
        doc = ReviewDocx('test')
        # Deliberately reverse input order; review_asset_ids were sorted by source locator.
        add_assets(doc, questions[0], {a['id']: a for a in reversed(assets)}, self.root)
        path = self.root / 'review.docx'
        doc.save(path)
        verified = verify_docx(path)
        self.assertEqual(verified['embedded_images'], 2)
        self.assertIn('image 1 | I1 | question_diagram', verified['image_labels'][0])
        self.assertIn('image 2 | I2 | solution_diagram', verified['image_labels'][1])
        with ZipFile(path) as archive:
            self.assertEqual(len([n for n in archive.namelist() if n.startswith('word/media/')]), 2)
            self.assertGreater(len(archive.read('word/media/image1.png')), 100)

    def test_role_is_provisional_and_solution_never_student_stem(self):
        _, assets = self.prepared()
        self.assertEqual([a['asset_role'] for a in assets], ['question_diagram', 'solution_diagram', 'unknown'])
        self.assertTrue(assets[0]['student_render_eligible_role'])
        self.assertFalse(assets[1]['student_render_eligible_role'])
        self.assertTrue(all(not a['student_render_enabled'] for a in assets))
        self.assertTrue(all(a['asset_role_status'] == 'suggested_pending_review' for a in assets))

    def test_missing_required_diagram_warns_and_never_approves(self):
        self.assets = self.assets[1:]
        self.questions[0]['asset_ids'] = ['I2']
        questions, assets = self.prepared()
        row = questions[0]
        self.assertTrue(row['missing_required_diagram'])
        self.assertIn('MISSING REQUIRED DIAGRAM', [w['detail'] for w in row['warnings']])
        self.assertEqual(row['review_group'], 'warning_candidates')
        self.assertEqual(row['decision'], 'pending')
        self.assertEqual(row['approval_suggestion'], 'none')
        doc = ReviewDocx('missing')
        originals = {str(self.source): [ET.Element(W + 'p') for _ in range(4)]}
        add_question(doc, row, {a['id']: a for a in assets}, self.root, originals)
        path = self.root / 'missing.docx'
        doc.save(path)
        with ZipFile(path) as archive:
            text = ''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
        self.assertIn('MISSING REQUIRED DIAGRAM', text)
        self.assertIn('decision: pending', text)

    def test_formula_warnings_require_source_check_and_do_not_guess(self):
        self.blocks[str(self.source)][0]['warnings'] = ['包含无法可靠转换的 OMML 公式']
        self.blocks[str(self.source)][0]['text'] += '[公式待核]'
        self.questions[0]['stem'] += '[公式待核]'
        questions, assets = self.prepared()
        row = questions[0]
        self.assertEqual(row['formula_status'], 'requires_source_check')
        self.assertEqual(row['decision'], 'pending')
        self.assertIn('[公式待核]', row['raw_candidate']['stem'])
        self.assertEqual(row['answer'], 'A')
        self.assertEqual(assets[2]['question_id'], None)

    def test_unlinked_keeps_null_and_pending(self):
        _, assets = self.prepared()
        unlinked = assets[2]
        self.assertIsNone(unlinked['question_id'])
        self.assertEqual(unlinked['human_action'], 'pending')
        self.assertEqual(unlinked['image_link_confidence'], 'unlinked')

    def test_decisions_initially_pending_and_repeat_preserves_human_input(self):
        questions, assets = self.prepared()
        path = self.root / 'decisions.jsonl'
        initialize_decisions(path, questions, assets)
        rows = read_rows(path)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r['decision'] == 'pending' for r in rows))
        rows[0]['decision'] = 'needs_fix'
        rows[0]['notes'] = 'manual note'
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        initialize_decisions(path, questions, assets)
        self.assertEqual(read_rows(path)[0]['decision'], 'needs_fix')
        self.assertEqual(read_rows(path)[0]['notes'], 'manual note')

    def test_media_hash_mismatch_invalidates_required_image(self):
        self.assets[0]['resources'][0]['sha256'] = 'incorrect'
        questions, assets = self.prepared()
        self.assertFalse(assets[0]['image_checks'][0]['legal'])
        self.assertTrue(questions[0]['missing_required_diagram'])

    def test_wrong_source_media_invalidates_binding(self):
        self.assets[0]['resources'][0]['package_part'] = 'word/media/image2.png'
        questions, assets = self.prepared()
        self.assertFalse(assets[0]['verification']['media_matches_source'])
        self.assertEqual(assets[0]['image_link_confidence'], 'low')
        self.assertTrue(questions[0]['missing_required_diagram'])

    def test_option_image_and_table_context(self):
        self.blocks[str(self.source)][1]['text'] = 'A.[图片待核]'
        _, assets = self.prepared()
        self.assertEqual(assets[0]['asset_role'], 'option_image')
        self.blocks[str(self.source)][1]['warnings'] = ['表格结构需人工核对']
        _, assets = self.prepared()
        self.assertEqual(assets[0]['asset_role'], 'unknown')
        self.assertEqual(assets[0]['image_link_confidence'], 'low')

    def test_native_math_is_not_flattened_or_repaired(self):
        paragraph = ET.fromstring(f'<w:p xmlns:w="{W[1:-1]}" xmlns:m="{M[1:-1]}"><m:oMath><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath></w:p>')
        original = ET.tostring(paragraph)
        doc = ReviewDocx('math')
        doc.native_source(paragraph)
        path = self.root / 'math.docx'
        doc.save(path)
        self.assertEqual(ET.tostring(paragraph), original)
        self.assertEqual(verify_docx(path)['native_math_count'], 1)

    def test_actual_objective_not_chapter_drives_knowledge(self):
        self.assertEqual(knowledge_suggestion('已知正方体，求点到平面的距离')['primary'], 'G008')
        self.assertEqual(knowledge_suggestion('若四棱锥的点运动，求轨迹长度')['primary'], 'G010')
        self.assertEqual(knowledge_suggestion('求圆柱的体积')['primary'], 'G001')

    def test_visual_count_can_detect_missing_second_image(self):
        self.blocks[str(self.source)][1]['text'] = '[图片待核][图片待核]'
        questions, _ = self.prepared()
        self.assertFalse(questions[0]['visual_count_check']['matches'])
        self.assertTrue(any(w['detail'] == '源图形数与关联实例数不一致' for w in questions[0]['warnings']))
