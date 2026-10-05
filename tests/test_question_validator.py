"""Validate completeness, taxonomy and explicit approval without network access."""

import tempfile
import unittest
from pathlib import Path
import json

from question_bank_helpers import candidate, approved
from services.question_validator import content_fingerprint, validate_candidate
from scripts.review_question_batch import review_batch
from unittest.mock import patch


class ValidatorTests(unittest.TestCase):
    def test_valid_reviewed_candidate_is_not_auto_approved(self):
        data = candidate()
        self.assertTrue(validate_candidate(data)["can_approve"])
        self.assertEqual(data["quality_status"], "reviewed")

    def test_missing_required_fields(self):
        for field in ("stem", "explanation", "source_file", "source_section", "source_locator", "id"):
            with self.subTest(field=field):
                self.assertFalse(validate_candidate(candidate(**{field: ""}))["valid"])

    def test_invalid_options_answer_knowledge_and_tags(self):
        changes = [{"options": {"A": "1", "B": "2", "C": "3"}}, {"answer": "AC"},
                   {"primary_knowledge_point_id": "K999"}, {"ability_tags": ["domain_analysis"]},
                   {"method_tags": ["new_method"]}, {"question_prerequisite_ids": ["K999"]},
                   {"related_knowledge_point_ids": ["K002"]}, {"difficulty": 6}, {"version": 0},
                   {"extraction_status": "approved"}, {"taxonomy_version": "function_v1"}]
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(validate_candidate(candidate(**change))["valid"])

    def test_fingerprint_content_and_answer_changes(self):
        original = candidate()
        self.assertEqual(len(original["fingerprint"]), 64)
        self.assertEqual(original["fingerprint"], candidate(source_file="other.docx")["fingerprint"])
        self.assertNotEqual(original["fingerprint"], candidate(answer="A")["fingerprint"])
        original["stem"] += "修改"
        self.assertFalse(validate_candidate(original)["valid"])

    def test_formula_image_short_and_explanation_warnings_block_approval(self):
        for change in ({"stem": "f(x)="}, {"stem": "如图，判断函数的变化。"},
                       {"explanation": "所以 f(x)="}, {"extraction_status": "formula_warning"},
                       {"explanation": "代入得到数值1，故选 A。"},
                       {"options": {"A": "f(x)=", "B": "2", "C": "3", "D": "4"}}):
            with self.subTest(change=change):
                self.assertFalse(validate_candidate(approved(**change))["can_approve"])

    def test_approval_needs_explicit_confirmation(self):
        self.assertFalse(validate_candidate(candidate(quality_status="approved"))["can_approve"])
        self.assertTrue(validate_candidate(approved())["can_approve"])

    def test_review_script_requires_per_question_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.jsonl"
            path.write_text(json.dumps(candidate(), ensure_ascii=False) + "\n", encoding="utf-8")
            decisions = iter(["approve", "教师", "confirm", ""])
            with patch("builtins.print"):
                review_batch(path, input_fn=lambda _: next(decisions))
            reviewed = json.loads((path.parent / "approved/batch_approved.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(reviewed["quality_status"], "approved")
            self.assertTrue(validate_candidate(reviewed)["can_approve"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["quality_status"], "reviewed")

    def test_review_script_cannot_approve_broken_question(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.jsonl"
            path.write_text(json.dumps(candidate(stem="f(x)=")), encoding="utf-8")
            decisions = iter(["approve", "q"])
            with patch("builtins.print"):
                review_batch(path, input_fn=lambda _: next(decisions))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["quality_status"], "reviewed")

    def test_question_number_is_not_part_of_dedup_identity(self):
        self.assertEqual(candidate(stem="1.函数 f(x)=2x+1，求 f(2) 的值。")["fingerprint"],
                         candidate(stem="7.函数 f(x)=2x+1，求 f(2) 的值。")["fingerprint"])

    def test_question_prerequisites_can_reference_advanced_integrated_content(self):
        self.assertTrue(validate_candidate(candidate(question_prerequisite_ids=["K010"]))["can_approve"])

    def test_ambiguous_log_fraction_requires_review(self):
        self.assertFalse(validate_candidate(candidate(explanation="代入公式 lg(I)/(I_(0)) 得到答案。"))["can_approve"])

    def test_empty_math_option_blocks_approval(self):
        self.assertFalse(validate_candidate(candidate(options={"A": "x^()", "B": "2", "C": "3", "D": "4"}))["can_approve"])

    def test_persisted_first_batch_is_valid_and_unapproved(self):
        path = Path(__file__).resolve().parents[1] / "data/question_bank/candidates/function_batch_001.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertGreater(len(rows), 0)
        self.assertLessEqual(len(rows), 30)
        self.assertEqual(len(rows), len({row["fingerprint"] for row in rows}))
        for row in rows:
            with self.subTest(candidate=row["id"]):
                self.assertEqual(row["quality_status"], "reviewed")
                self.assertTrue(validate_candidate(row)["can_approve"])
