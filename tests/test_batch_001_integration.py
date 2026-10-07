"""Batch 001 gold approval and disposable v2 integration acceptance."""

from collections import Counter
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from runtime_helpers import use_v1_test_config
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from database.database import get_connection, record_attempt, DATABASE_PATH
from question_bank_helpers import approved
from scripts.review_question_batch import DEFAULT_BATCH, output_paths
from scripts.verify_question_review import verify_approved_batch
from services.feedback import build_feedback_context, build_rule_based_feedback
from services.mastery import calculate_student_mastery, calculate_knowledge_mastery
from services.question_bank_coverage import build_coverage_report, write_gap_report
from services.question_bank_sandbox import create_sandbox, bank_service_context, training_questions, sandbox_recommendation
from services.question_importer import import_questions
from services.question_review import approve_confirmed_batch, read_jsonl
from services.recommendation import recommend_questions

ROOT = Path(__file__).resolve().parents[1]


class BatchIntegrationTests(unittest.TestCase):
    def setUp(self):
        use_v1_test_config(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "candidates/function_batch_001.jsonl"
        self.snapshot.parent.mkdir()
        self.snapshot.write_bytes(DEFAULT_BATCH.read_bytes())
        self.digest = hashlib.sha256(self.snapshot.read_bytes()).hexdigest()
        self.rows = read_jsonl(self.snapshot)
        self.path = self.root / "sandbox.db"

    def approve_batch(self):
        return approve_confirmed_batch(self.snapshot, *output_paths(self.snapshot))

    def make_sandbox(self, rows=None):
        if rows is None: rows = read_jsonl(self.approve_batch().approved)
        create_sandbox(self.path, rows)
        return rows

    def train(self, question_id, correct=1, student="TEST", times=1):
        for _ in range(times):
            record_attempt(student, question_id, "C", correct, 1.5, database_path=self.path)

    def test_all_29_user_confirmed_exports_have_audit_and_unique_fingerprints(self):
        session = self.approve_batch()
        gold = read_jsonl(session.approved)
        self.assertEqual(len(gold), 29)
        self.assertEqual(len({row["fingerprint"] for row in gold}), 29)
        self.assertEqual(len({row["id"] for row in gold}), 29)
        for row in gold:
            self.assertEqual(row["quality_status"], "approved")
            self.assertEqual(row["reviewed_by"], "manual_user")
            self.assertTrue(row["reviewed_at"])
            self.assertIn("用户已基于可读版题目完成人工审核，确认题干、选项、答案、解析及题目分类可接受。", row["review_notes"])
        self.assertEqual(hashlib.sha256(self.snapshot.read_bytes()).hexdigest(), self.digest)

    def test_bad_question_stops_entire_batch_before_any_approval(self):
        self.rows[10]["answer"] = "E"
        self.snapshot.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in self.rows), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, self.rows[10]["id"]):
            self.approve_batch()
        self.assertFalse(output_paths(self.snapshot)[0].exists())

    def test_wrong_batch_size_stops_approval(self):
        self.snapshot.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in self.rows[:28]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "28"):
            self.approve_batch()

    def test_duplicate_fingerprint_stops_approval(self):
        self.rows[1] = {**self.rows[0], "id": "DUPLICATE"}
        self.snapshot.write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in self.rows), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.approve_batch()

    def test_actual_first_import_29_second_zero_skipped_29(self):
        result = verify_approved_batch(self.approve_batch().approved)
        self.assertEqual(result["inserted"], 29)
        self.assertEqual(result["inserted_on_repeat"], 0)
        self.assertEqual(result["skipped_on_repeat"], 29)
        self.assertEqual(result["unapproved_rejected"], 87)

    def test_approved_only_training_and_private_metadata_hidden(self):
        self.make_sandbox()
        rows = training_questions(self.path)
        self.assertEqual(len(rows), 29)
        for row in rows:
            self.assertEqual(set(row["options"]), set("ABCD"))
            for field in ("fingerprint", "source_file", "review_notes", "taxonomy_version"):
                self.assertNotIn(field, row)
        for status in ("reviewed", "draft", "rejected"):
            result = import_questions([{**approved(id=status), "quality_status": status}], database_path=self.path)
            self.assertEqual(result["inserted"], 0)
        self.assertEqual(len(training_questions(self.path)), 29)

    def test_sql_approval_gate_excludes_legacy_question(self):
        self.make_sandbox()
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("INSERT INTO questions SELECT 'UNAPPROVED',stem,options,answer,explanation,knowledge_point_id,difficulty,ability_tag,question_type,estimated_time FROM questions LIMIT 1")
        self.assertNotIn("UNAPPROVED", [row["id"] for row in training_questions(self.path)])

    def test_all_15_untrained_points_are_none_despite_bank_population(self):
        self.make_sandbox()
        with bank_service_context(self.path, "TEST"):
            results = calculate_student_mastery("TEST")
        self.assertEqual(len(results), 15)
        self.assertTrue(all(row["mastery_score"] is None and row["mastery_level"] == "未评估" for row in results))

    def test_related_points_receive_no_duplicate_mastery_evidence(self):
        bank = self.make_sandbox()
        question = next(row for row in bank if row["related_knowledge_point_ids"])
        self.train(question["id"])
        with bank_service_context(self.path, "TEST"):
            results = calculate_student_mastery("TEST")
        counts = {row["knowledge_point_id"]: row["attempt_count"] for row in results}
        self.assertEqual(sum(counts.values()), 1)
        self.assertEqual(counts[question["primary_knowledge_point_id"]], 1)
        self.assertTrue(all(counts[key] == 0 for key in question["related_knowledge_point_ids"]))

    def test_old_q005_q006_cannot_contaminate_new_odd_even_k005(self):
        self.make_sandbox()
        with closing(get_connection(self.path)) as connection:
            with connection:
                for key in ("Q005", "Q006"):
                    connection.execute("INSERT INTO questions SELECT ?,stem,options,answer,explanation,'K005',difficulty,ability_tag,question_type,estimated_time FROM questions LIMIT 1", (key,))
        self.train("Q005"); self.train("Q006")
        with bank_service_context(self.path, "TEST"):
            result = calculate_knowledge_mastery("TEST", "K005")
        self.assertEqual(result["knowledge_point_name"], "函数奇偶性")
        self.assertEqual(result["attempt_count"], 0)
        self.assertIsNone(result["mastery_score"])

    def test_question_prerequisites_block_until_verified(self):
        rows = [approved(id="BASE", primary_knowledge_point_id="K001"),
                approved(id="DOMAIN", stem="求函数 f(x)=4x+1 的值。", primary_knowledge_point_id="K002"),
                approved(id="TARGET", stem="函数 f(x)=2x+1，求 f(2) 并判断单调性。", primary_knowledge_point_id="K003", question_prerequisite_ids=["K001"])]
        self.make_sandbox(rows)
        with bank_service_context(self.path, "TEST"):
            self.assertEqual(recommend_questions("TEST", "K003"), [])
        self.train("BASE")
        self.train("DOMAIN")
        with bank_service_context(self.path, "TEST"):
            self.assertEqual([row["id"] for row in recommend_questions("TEST", "K003")], ["TARGET"])

    def test_recommendation_respects_core_prerequisites(self):
        rows = [approved(id="K1", primary_knowledge_point_id="K001"),
                approved(id="K2", primary_knowledge_point_id="K002", stem="求函数 f(x)=3x+1 的值。"),
                approved(id="K3", primary_knowledge_point_id="K003", stem="判断函数 f(x)=x+1 的单调性。")]
        self.make_sandbox(rows)
        self.train("K3", 0, times=6)
        result = sandbox_recommendation("TEST", self.path)
        self.assertEqual(result["target_knowledge"]["knowledge_point_id"], "K001")

    def test_recent_question_is_ranked_after_unseen_question(self):
        rows = [approved(id="OLD", primary_knowledge_point_id="K001"),
                approved(id="NEW", primary_knowledge_point_id="K001", stem="求函数 f(x)=3x+1 的值。")]
        self.make_sandbox(rows)
        self.train("OLD")
        with bank_service_context(self.path, "TEST"):
            questions = recommend_questions("TEST", "K001")
        self.assertEqual([row["id"] for row in questions], ["NEW", "OLD"])

    def test_k007_empty_has_friendly_coverage_status(self):
        bank = self.make_sandbox()
        for row in bank:
            self.train(row["id"])
        result = sandbox_recommendation("TEST", self.path)
        self.assertEqual(result["target_knowledge"]["knowledge_point_id"], "K007")
        self.assertEqual(result["status"], "insufficient_coverage")
        self.assertIn("暂无金标准题", result["message"])

    def test_training_page_new_question_submit_explanation_and_no_source(self):
        self.make_sandbox()
        first = training_questions(self.path)[0]
        with bank_service_context(self.path):
            page = AppTest.from_file(str(ROOT / "pages/training.py")).run()
            self.assertEqual(len(page.exception), 0)
            self.assertEqual(page.text[0].value, first["stem"])
            self.assertEqual(len(page.radio[0].options), 4)
            page.radio[0].set_value(first["answer"]).run()
            page.button[0].click().run()
            self.assertEqual(page.success[0].value, "回答正确")
            self.assertTrue(any(item.value == first["explanation"] for item in page.text))
            text = "\n".join(str(element.value) for kind in ("text", "markdown", "caption") for element in page.get(kind))
            for secret_field in ("source_file", "fingerprint", "review_notes", "function_v2"):
                self.assertNotIn(secret_field, text)

    def test_profile_and_feedback_pages_support_15_points_without_api(self):
        self.make_sandbox()
        with bank_service_context(self.path), patch("services.feedback.generate_text", side_effect=AssertionError("不能调用 API")) as api:
            profile = AppTest.from_file(str(ROOT / "pages/profile.py")).run()
            self.assertEqual(len(profile.exception), 0)
            self.assertEqual(len(profile.expander), 15)
            feedback = AppTest.from_file(str(ROOT / "pages/feedback.py")).run()
            self.assertEqual(len(feedback.exception), 0)
            next(button for button in feedback.button if button.label == "查看规则式学习反馈").click().run()
            self.assertEqual(len(feedback.exception), 0)
            api.assert_not_called()

    def test_coverage_thresholds_distribution_and_p0(self):
        rows = read_jsonl(self.approve_batch().approved)
        coverage = build_coverage_report(rows)
        points = {p["knowledge_point_id"]: p for p in coverage["points"]}
        self.assertEqual(points["K007"]["approved_count"], 0)
        self.assertEqual(points["K007"]["priority"], "P0")
        self.assertEqual(points["K002"]["status"], "sufficient_coverage")
        self.assertEqual(points["K001"]["status"], "insufficient_coverage")
        self.assertEqual(sum(p["approved_count"] for p in points.values()), 29)
        self.assertEqual(coverage["suggested_order"][0], "K007")

    def test_coverage_ignores_unapproved_and_does_not_mutate_inputs(self):
        rows = [approved(), {**approved(), "quality_status": "reviewed"}, {**approved(), "quality_status": "draft"}]
        before = deepcopy(rows)
        self.assertEqual(sum(p["approved_count"] for p in build_coverage_report(rows)["points"]), 1)
        self.assertEqual(rows, before)

    def test_gap_report_does_not_generate_second_batch(self):
        path = self.root / "gap.md"
        write_gap_report(read_jsonl(self.approve_batch().approved), path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("K007", text)
        self.assertIn("P0", text)
        self.assertIn("insufficient_coverage", text)
        self.assertFalse((self.root / "function_batch_002.jsonl").exists())

    def test_sandbox_refuses_real_database(self):
        with self.assertRaises(ValueError):
            create_sandbox(DATABASE_PATH, [])

    def test_coverage_p2_p3_and_p4_thresholds(self):
        for difficulty, priority in ((3, "P2"), (1, "P3"), (2, "P4")):
            rows = [approved(id=f"C{i}", difficulty=difficulty) for i in range(3)]
            point = next(row for row in build_coverage_report(rows)["points"] if row["knowledge_point_id"] == "K002")
            self.assertEqual(point["priority"], priority)

    def test_weak_question_prerequisite_blocks_recommendation(self):
        rows = [approved(id="BASE", primary_knowledge_point_id="K001"),
                approved(id="DOMAIN", stem="求函数 f(x)=4x+1 的值。", primary_knowledge_point_id="K002"),
                approved(id="TARGET", stem="函数 f(x)=2x+1，求 f(2) 并判断单调性。", primary_knowledge_point_id="K003", question_prerequisite_ids=["K008"])]
        self.make_sandbox(rows)
        self.train("BASE"); self.train("DOMAIN")
        with bank_service_context(self.path, "TEST"):
            self.assertEqual(recommend_questions("TEST", "K003"), [])
