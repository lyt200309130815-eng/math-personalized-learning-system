"""Offline human-review workflow acceptance using synthetic snapshots and temp DBs."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from runtime_helpers import use_v1_test_config
from unittest.mock import patch

from question_bank_helpers import candidate
from scripts.review_question_batch import review_batch, output_paths, review_lock
from scripts.verify_question_review import verify_approved_batch
from services.question_review import ReviewSession, read_jsonl


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        use_v1_test_config(self)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.snapshot = self.root / "candidates/function_batch_001.jsonl"
        self.snapshot.parent.mkdir()
        self.rows = [candidate(id=f"TEST-{i}", stem=f"函数 f(x)=2x+{i}，求 f(2) 的值。") for i in range(1, 4)]
        self.write_snapshot()

    def write_snapshot(self):
        self.snapshot.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in self.rows), encoding="utf-8")
        self.digest = hashlib.sha256(self.snapshot.read_bytes()).hexdigest()

    def session(self):
        return ReviewSession(self.snapshot, *output_paths(self.snapshot))

    def test_prepare_does_not_review_or_change_snapshot(self):
        with patch("builtins.print"):
            session = review_batch(self.snapshot, prepare_only=True, input_fn=lambda _: self.fail("不应要求审核"))
        self.assertEqual(session.latest, {})
        self.assertEqual(read_jsonl(session.approved), [])
        self.assertEqual(hashlib.sha256(self.snapshot.read_bytes()).hexdigest(), self.digest)
        self.assertIn("候选总数：3", session.report.read_text(encoding="utf-8"))

    def test_approve_reject_skip_and_audit_metadata(self):
        session = self.session()
        session.decide("TEST-1", "approve", "教师甲", "答案解析已核对", confirmed=True)
        session.decide("TEST-2", "reject", "教师甲", "答案待修订")
        session.decide("TEST-3", "skip", "教师甲", "稍后复核")
        self.assertEqual([row["quality_status"] for row in read_jsonl(session.reviews)], ["approved", "rejected", "reviewed"])
        self.assertEqual([row["id"] for row in read_jsonl(session.approved)], ["TEST-1"])
        for row in read_jsonl(session.reviews):
            self.assertEqual(row["reviewed_by"], "教师甲")
            self.assertIn("+00:00", row["reviewed_at"])
            self.assertTrue(row["review_notes"])
        self.assertEqual(hashlib.sha256(self.snapshot.read_bytes()).hexdigest(), self.digest)

    def test_quit_and_resume_start_at_first_unreviewed_question(self):
        answers = iter(["a", "confirm", "核对完成", "q"])
        with patch("builtins.print"):
            review_batch(self.snapshot, reviewer="教师", input_fn=lambda _: next(answers))
        self.assertEqual([row["id"] for row in self.session().pending()], ["TEST-2", "TEST-3"])
        with patch("scripts.review_question_batch.display_candidate") as display:
            review_batch(self.snapshot, reviewer="教师", input_fn=lambda _: "q")
        self.assertEqual(display.call_args[0][0]["id"], "TEST-2")

    def test_revisit_skipped_is_explicit_and_does_not_duplicate_gold(self):
        session = self.session()
        session.decide("TEST-1", "skip", "教师")
        self.assertNotIn("TEST-1", [row["id"] for row in self.session().pending()])
        self.assertIn("TEST-1", [row["id"] for row in self.session().pending(revisit_skipped=True)])
        session.decide("TEST-1", "approve", "教师", confirmed=True)
        self.assertEqual(len(read_jsonl(session.approved)), 1)
        self.assertEqual(len(read_jsonl(session.reviews)), 2)

    def test_non_complete_and_warning_cannot_be_approved(self):
        for status in ("formula_warning", "image_required", "incomplete", "manual_review"):
            with self.subTest(status=status):
                self.rows[0]["extraction_status"] = status
                self.write_snapshot()
                with self.assertRaises(ValueError):
                    self.session().decide("TEST-1", "approve", "教师", "核对过也不能静默覆盖", confirmed=True)

    def test_validator_is_run_again_at_approval(self):
        session = self.session()
        with patch("services.question_review.validate_candidate", return_value={"can_approve": False}) as validator:
            with self.assertRaises(ValueError):
                session.decide("TEST-1", "approve", "教师", confirmed=True)
        validator.assert_called()
        self.assertFalse(session.reviews.exists())

    def test_explicit_confirmation_and_reviewer_are_required(self):
        for name, confirmation in (("", True), ("教师", False)):
            with self.assertRaises(ValueError):
                self.session().decide("TEST-1", "approve", name, confirmed=confirmation)

    def test_fingerprint_mismatch_blocks_approval(self):
        self.rows[0]["stem"] += "内容被修改但未更新指纹"
        self.write_snapshot()
        with self.assertRaises(ValueError):
            self.session().decide("TEST-1", "approve", "教师", confirmed=True)

    def test_review_report_counts_distributions_and_missing_k007(self):
        session = self.session()
        session.decide("TEST-1", "approve", "教师", confirmed=True)
        session.decide("TEST-2", "reject", "教师")
        session.decide("TEST-3", "skip", "教师")
        report = session.report.read_text(encoding="utf-8")
        for value in ("approved：1", "rejected：1", "skipped/reviewed：1", "| calculation | 1 |",
                      "| substitution | 1 |", "| 1 | 1 |", "K007 暂无金标准题，需要 Batch 002 定向补充。"):
            self.assertIn(value, report)

    def test_changed_snapshot_prevents_resume(self):
        self.session().decide("TEST-1", "skip", "教师")
        self.snapshot.write_text(self.snapshot.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.session()

    def test_tampered_review_content_cannot_be_exported(self):
        session = self.session()
        session.decide("TEST-1", "approve", "教师", confirmed=True)
        rows = read_jsonl(session.reviews)
        rows[0]["source_locator"] = "伪造页码"
        session.reviews.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.session()

    def test_interrupted_export_is_rebuilt_from_committed_journal(self):
        session = self.session()
        with patch.object(session, "save_outputs", side_effect=OSError("模拟导出中断")):
            with self.assertRaises(OSError):
                session.decide("TEST-1", "approve", "教师", confirmed=True)
        recovered = self.session()
        recovered.save_outputs()
        self.assertEqual([row["id"] for row in read_jsonl(recovered.approved)], ["TEST-1"])
        self.assertEqual(len(recovered.pending()), 2)

    def test_output_cannot_overwrite_candidate_snapshot(self):
        with self.assertRaises(ValueError):
            ReviewSession(self.snapshot, self.snapshot, self.root / "approved.jsonl", self.root / "report.md")
        self.assertEqual(hashlib.sha256(self.snapshot.read_bytes()).hexdigest(), self.digest)

    def test_concurrent_review_is_refused(self):
        path = self.root / "review.lock"
        with review_lock(path):
            with self.assertRaises(FileExistsError):
                with review_lock(path):
                    self.fail("不应获取第二把锁")
        self.assertFalse(path.exists())

    def test_empty_approved_file_has_friendly_temporary_db_result(self):
        session = self.session()
        session.save_outputs()
        result = verify_approved_batch(session.approved)
        self.assertEqual(result["inserted"], 0)
        self.assertIn("暂无金标准题", result["empty_bank_message"])
        self.assertIn("K007", result["empty_knowledge_points"])
        self.assertFalse(result["real_database_modified"])

    def test_approved_temporary_import_is_idempotent_and_business_compatible(self):
        self.rows[0]["related_knowledge_point_ids"] = ["K003", "K007"]
        self.write_snapshot()
        session = self.session()
        session.decide("TEST-1", "approve", "教师", confirmed=True)
        session.decide("TEST-2", "reject", "教师")
        session.decide("TEST-3", "skip", "教师")
        result = verify_approved_batch(session.approved)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped_on_repeat"], 1)
        self.assertEqual(result["unapproved_rejected"], 3)
        self.assertEqual(result["training_count"], 1)
        self.assertTrue(result["legacy_unchanged"])
        self.assertEqual(result["preserved_legacy_attempt_count"], 1)
        self.assertTrue(result["source_traceable"])
        self.assertIn("PASS", result["mastery_profile_recommendation_feedback"])

    def test_verification_rejects_unapproved_file(self):
        for status in ("reviewed", "rejected"):
            path = self.root / "not_gold.jsonl"
            row = deepcopy(self.rows[0])
            row["quality_status"] = status
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_approved_batch(path)

    def test_temporary_acceptance_never_calls_llm(self):
        session = self.session()
        session.save_outputs()
        with patch("services.feedback.generate_text", side_effect=AssertionError("禁止真实 API")) as llm:
            verify_approved_batch(session.approved)
        llm.assert_not_called()

    def test_temporary_import_deduplicates_matching_fingerprints(self):
        self.rows[1] = {**self.rows[0], "id": "TEST-2", "source_file": "another-source.docx"}
        self.write_snapshot()
        session = self.session()
        session.decide("TEST-1", "approve", "教师", confirmed=True)
        session.decide("TEST-2", "approve", "教师", confirmed=True)
        result = verify_approved_batch(session.approved)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped_on_repeat"], 2)
        self.assertEqual(result["training_count"], 1)
