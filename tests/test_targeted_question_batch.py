"""Offline Batch 002 contracts and conservative cross-batch deduplication."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.extract_targeted_question_batch import projection_rows, select_questions, write_new_outputs
from services.question_deduplication import DuplicateIndex, normalize_stem, quadratic_primary
from services.question_review import read_jsonl
from services.question_validator import load_taxonomy, validate_candidate

ROOT = Path(__file__).resolve().parents[1]


class TargetedBatchTests(unittest.TestCase):
    def setUp(self):
        self.old = read_jsonl(ROOT / 'data/question_bank/candidates/function_batch_001.jsonl')
        self.approved = read_jsonl(ROOT / 'data/question_bank/approved/function_batch_001_approved.jsonl')
        self.batch = read_jsonl(ROOT / 'data/question_bank/candidates/function_batch_002.jsonl')

    def test_no_cross_batch_or_internal_duplicates(self):
        index = DuplicateIndex(self.old + self.approved)
        for row in self.batch:
            self.assertEqual(index.reasons(row), [], row['id'])
            index.add(row)

    def test_fingerprint_identity_with_different_id_and_source(self):
        old = self.batch[0]
        copy = deepcopy(old)
        copy.update(id='different', stem='完全不同题干', source_file='other.docx', source_locator='other', source_question_number=None)
        self.assertIn('fingerprint', DuplicateIndex([old]).reasons(copy))

    def test_whitespace_and_full_width_normalization(self):
        self.assertEqual(normalize_stem('1. 函数ｆ（ｘ）＝２ｘ'), normalize_stem('1.函数 f(x)=2x'))
        row = deepcopy(self.batch[0])
        changed = deepcopy(row)
        changed.update(id='new', fingerprint='new', stem=row['stem'].replace(' ', '') + '\n',
                       source_file='other', source_locator='other', source_question_number=None)
        self.assertIn('normalized_stem', DuplicateIndex([row]).reasons(changed))

    def test_source_locator_and_original_number_deduplicate(self):
        row = deepcopy(self.batch[0])
        other = deepcopy(row)
        other.update(id='new', fingerprint='new', stem='不同内容仍然不能复用来源')
        self.assertIn('source_locator', DuplicateIndex([row]).reasons(other))
        other['source_locator'] = 'different'
        self.assertIn('source_question_number', DuplicateIndex([row]).reasons(other))

    def test_all_selected_are_reviewed_complete_and_valid_utf8(self):
        self.assertGreaterEqual(len(self.batch), 22)
        self.assertLessEqual(len(self.batch), 30)
        for row in self.batch:
            self.assertEqual(row['quality_status'], 'reviewed')
            self.assertEqual(row['extraction_status'], 'complete')
            self.assertEqual(row['question_type'], 'single_choice')
            self.assertTrue(validate_candidate(row)['can_approve'], row['id'])
            self.assertNotIn('\ufffd', json.dumps(row, ensure_ascii=False))
        self.assertIn('函数', (ROOT / 'data/question_bank/candidates/function_batch_002.jsonl').read_text(encoding='utf-8'))

    def test_basic_quadratic_objectives_qualify_without_quota_relabeling(self):
        self.assertEqual(quadratic_primary('二次函数的顶点与对称轴是什么？'), 'K007')
        self.assertEqual(quadratic_primary('二次函数在区间上的最大值是多少？'), 'K004')
        self.assertEqual(quadratic_primary('二次函数的单调区间是什么？'), 'K003')
        self.assertEqual(quadratic_primary('二次函数的值域是什么？'), 'K002')
        # Existing materials have no reliable basic quadratic single-choice item.
        # Report the unmet target rather than fabricating or reclassifying one.
        self.assertFalse(any(row['primary_knowledge_point_id'] == 'K007' for row in self.batch))
        report = (ROOT / 'reports/question_import_batch_002.md').read_text(encoding='utf-8')
        self.assertIn('无法达到至少3道目标', report)
        quadratic_max = next(row for row in self.batch if row['id'] == 'FC-ba01c7b6e4605f9c')
        self.assertEqual(quadratic_max['primary_knowledge_point_id'], 'K004')

    def test_pending_items_are_not_reviewed_or_approved(self):
        pending = read_jsonl(ROOT / 'data/question_bank/review_required/function_batch_002.jsonl')
        self.assertTrue(pending)
        for row in pending:
            self.assertEqual(row['quality_status'], 'draft')
            self.assertFalse(validate_candidate(row)['can_approve'])

    def test_projection_separates_actual_and_hypothetical_coverage(self):
        before = deepcopy(self.batch)
        rows = projection_rows(self.approved, self.batch, load_taxonomy()['knowledge_points'])
        self.assertEqual(sum(row['current_approved'] for row in rows), 29)
        self.assertEqual(sum(row['candidate_reviewed'] for row in rows), len(self.batch))
        self.assertEqual(sum(row['projected_total'] for row in rows), 29 + len(self.batch))
        self.assertEqual(self.batch, before)
        self.assertEqual(next(row for row in rows if row['id'] == 'K007')['projected_total'], 0)

    def test_selection_does_not_modify_input_or_promote_to_approved(self):
        row = deepcopy(self.batch[0])
        before = deepcopy(row)
        annotation = {key: row[key] for key in ('id', 'primary_knowledge_point_id', 'difficulty',
                     'related_knowledge_point_ids', 'question_prerequisite_ids', 'ability_tags', 'method_tags')}
        annotation['annotation_reason'] = '供人工核对。'
        selected, _, _ = select_questions([row, row], [], [annotation])
        self.assertEqual(len(selected), 1)
        self.assertEqual(row, before)
        self.assertEqual(selected[0]['quality_status'], 'reviewed')

    def test_existing_snapshots_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / 'existing.jsonl'
            existing.write_text('原始快照', encoding='utf-8')
            new = Path(directory) / 'new.jsonl'
            with self.assertRaises(FileExistsError):
                write_new_outputs({new: 'new', existing: 'overwrite'})
            self.assertEqual(existing.read_text(encoding='utf-8'), '原始快照')
            self.assertFalse(new.exists())

    def test_selection_never_opens_database_and_preserves_real_db(self):
        from unittest.mock import patch
        database = ROOT / 'math_ai.db'
        digest = hashlib.sha256(database.read_bytes()).hexdigest() if database.exists() else None
        with patch('sqlite3.connect', side_effect=AssertionError('数据库不应被打开')):
            select_questions(self.batch, self.old + self.approved, [])
        if digest:
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), digest)
