"""Batch 002 approval and exactly eleven original, unapproved gap-fill items."""

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from scripts.prepare_original_gap_questions import build_original_questions, verify_original_math, write_readable_docx
from scripts.verify_question_review import verify_approved_batch
from services.question_bank_coverage import build_coverage_report
from services.question_deduplication import DuplicateIndex
from services.question_importer import import_questions
from services.question_review import approve_confirmed_batch, read_jsonl, ReviewSession
from services.question_validator import validate_candidate

ROOT=Path(__file__).resolve().parents[1]
NOTES='用户已基于可读版完成人工审核，确认题干、公式、选项、答案、解析及分类可接受。'
SNAPSHOT=ROOT/'data/question_bank/candidates/function_batch_002.jsonl'
GOLD=ROOT/'data/question_bank/approved/function_batch_002_approved.jsonl'
ORIGINAL=ROOT/'data/question_bank/candidates/function_batch_003_original.jsonl'


class OriginalGapBatchTests(unittest.TestCase):
    def setUp(self):
        self.originals=read_jsonl(ORIGINAL)
        self.gold=read_jsonl(GOLD)
        self.previous=read_jsonl(ROOT/'data/question_bank/approved/function_batch_001_approved.jsonl')

    def test_batch002_all_26_approved_with_exact_user_audit(self):
        session=ReviewSession(SNAPSHOT,ROOT/'data/question_bank/reviews/function_batch_002_review.jsonl',
                              GOLD,ROOT/'reports/question_review_batch_002.md')
        self.assertEqual(len(self.gold),26)
        self.assertEqual(len(session.latest),26)
        for q in self.gold:
            self.assertEqual(q,session.latest[q['id']])
            self.assertEqual(q['quality_status'],'approved')
            self.assertEqual(q['reviewed_by'],'manual_user')
            self.assertIn(NOTES,q['review_notes'])
            self.assertTrue(validate_candidate(q)['can_approve'])

    def test_batch002_candidate_original_content_and_status_preserved(self):
        self.assertEqual(hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
                         'cbccf1d5b5663852a09e25ba15749796c4e6283acf26cc247487755549bddad6')
        candidates=read_jsonl(SNAPSHOT)
        self.assertTrue(all(q['quality_status']=='reviewed' for q in candidates))
        for candidate,gold in zip(candidates,self.gold):
            for field in ('id','stem','options','answer','explanation','fingerprint'):
                self.assertEqual(candidate[field],gold[field])

    def test_batch002_temp_import_first26_repeat0_skipped26(self):
        result=verify_approved_batch(GOLD)
        self.assertEqual((result['inserted'],result['inserted_on_repeat'],result['skipped_on_repeat']),(26,0,26))
        self.assertTrue(result['legacy_unchanged'])

    def test_failed_batch002_preflight_creates_no_approval_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); snapshot=root/'batch.jsonl'
            rows=read_jsonl(SNAPSHOT); rows[2]['answer']='INVALID'
            snapshot.write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in rows),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,rows[2]['id']):
                approve_confirmed_batch(snapshot,root/'reviews',root/'approved',root/'report',expected_count=26,review_notes=NOTES)
            self.assertFalse((root/'approved').exists())
            self.assertFalse((root/'reviews').exists())

    def test_exactly_eleven_originals(self):
        self.assertEqual(len(self.originals),11)
        self.assertEqual(build_original_questions(),self.originals)

    def test_k001_two_true_concept_questions(self):
        rows=[q for q in self.originals if q['primary_knowledge_point_id']=='K001']
        self.assertEqual(len(rows),2)
        self.assertIn('对应关系',rows[0]['stem'])
        self.assertIn('同一个函数',rows[1]['stem'])

    def test_k007_five_basic_quadratic_objectives(self):
        rows=[q for q in self.originals if q['primary_knowledge_point_id']=='K007']
        self.assertEqual(len(rows),5)
        for q,objective in zip(rows,('二次函数','对称轴','顶点','开口方向','解析式')):
            self.assertIn(objective,q['stem'])
            self.assertNotIn('最大值',q['stem'])
            self.assertNotIn('最小值',q['stem'])
            self.assertNotIn('单调',q['stem'])
            self.assertEqual(q['related_knowledge_point_ids'],[])
        self.assertEqual(Counter(q['difficulty'] for q in rows),{1:2,2:2,3:1})

    def test_k009_two_basic_exponential_questions(self):
        rows=[q for q in self.originals if q['primary_knowledge_point_id']=='K009']
        self.assertEqual(len(rows),2)
        self.assertEqual([q['difficulty'] for q in rows],[1,2])
        self.assertIn('定义',rows[0]['stem'])
        self.assertIn('图象',rows[1]['stem'])

    def test_k005_one_domain_sensitive_basic_question(self):
        rows=[q for q in self.originals if q['primary_knowledge_point_id']=='K005']
        self.assertEqual(len(rows),1)
        self.assertIn('定义域',rows[0]['stem'])
        self.assertIn('不关于原点对称',rows[0]['explanation'])
        self.assertEqual(rows[0]['difficulty'],2)

    def test_k014_one_equation_intersection_conversion(self):
        rows=[q for q in self.originals if q['primary_knowledge_point_id']=='K014']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['difficulty'],2)
        self.assertIn('图象交点',rows[0]['stem'])
        self.assertIn('x²=x+2',rows[0]['stem'])
        self.assertEqual(rows[0]['question_prerequisite_ids'],['K007'])

    def test_all_original_reviewed_never_approved(self):
        for q in self.originals:
            self.assertEqual(q['quality_status'],'reviewed')
            self.assertNotIn('reviewed_by',q)
            self.assertTrue(validate_candidate(q)['can_approve'])
        # The candidate remains reviewed even after a separately authorized approval export.

    def test_source_type_and_reference_and_independent_ids(self):
        for q in self.originals:
            self.assertEqual(q['source_type'],'original')
            self.assertEqual(q['source_ref'],'V0.8G-original-gap-fill')
            self.assertTrue(q['id'].startswith('Q-ORG-F-'))
            self.assertEqual(q['question_type'],'single_choice')

    def test_fingerprints_unique_and_cross_batch_deduplication(self):
        self.assertEqual(len({q['fingerprint'] for q in self.originals}),11)
        index=DuplicateIndex(self.previous+self.gold)
        for q in self.originals:
            self.assertEqual(index.reasons(q),[])
            index.add(q)

    def test_mathematical_verification_unique_answers_and_wrong_answer_rejected(self):
        for q in self.originals:
            self.assertEqual(verify_original_math(q),q['validation_notes'])
            incorrect=deepcopy(q)
            incorrect['answer']=next(k for k in 'ABCD' if k!=q['answer'])
            with self.assertRaisesRegex(ValueError,'数学验证失败'):
                verify_original_math(incorrect)

    def test_originals_cannot_be_imported_even_with_program_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            result=import_questions(self.originals,database_path=Path(directory)/'test.db')
            self.assertEqual(result['inserted'],0)
            self.assertEqual(result['rejected'],11)

    def test_projected_coverage_sufficient_but_real_coverage_still_incomplete(self):
        current=build_coverage_report(self.previous+self.gold)
        self.assertEqual(sum(p['approved_count'] for p in current['points']),55)
        self.assertEqual({p['knowledge_point_id'] for p in current['points'] if p['gaps']},
                         {'K001','K005','K007','K009','K014'})
        projected=build_coverage_report(self.previous+self.gold+[{**q,'quality_status':'approved'} for q in self.originals])
        self.assertEqual(projected['status'],'sufficient_coverage')
        self.assertEqual(sum(p['approved_count'] for p in projected['points']),66)
        self.assertTrue(all(q['quality_status']=='reviewed' for q in self.originals))

    def test_readable_word_has_eleven_questions_no_internal_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            docx=Path(directory)/'readable.docx'
            write_readable_docx(self.originals,docx)
            with ZipFile(docx) as archive:
                self.assertIsNone(archive.testzip())
                text=''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
            self.assertEqual(text.count('主要知识点：'),11)
            for label in ('fingerprint','taxonomy_version','source_ref','hash','JSON'):
                self.assertNotIn(label,text)
            self.assertIn('x²−6x+5',text)

    def test_original_creation_never_connects_to_database_or_modifies_attempts(self):
        real=ROOT/'math_ai.db'
        before=hashlib.sha256(real.read_bytes()).hexdigest() if real.exists() else None
        with patch('sqlite3.connect',side_effect=AssertionError('不应打开数据库')):
            build_original_questions()
        if before:
            self.assertEqual(hashlib.sha256(real.read_bytes()).hexdigest(),before)
