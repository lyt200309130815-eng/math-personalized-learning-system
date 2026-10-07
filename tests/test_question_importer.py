"""Approved-only isolated imports preserve all legacy evidence."""

from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from runtime_helpers import use_v1_test_config

from database.database import DATABASE_PATH, get_connection, record_attempt
from init_db import initialize_database
from services.feedback import build_feedback_context, build_rule_based_feedback
from services.mastery import calculate_student_mastery
from services.question_importer import get_approved_questions, import_questions
from services.recommendation import generate_recommendation
from services.recommendation import recommend_questions
from unittest.mock import patch
from question_bank_helpers import candidate, approved


class ImporterTests(unittest.TestCase):
    def setUp(self):
        use_v1_test_config(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "isolated.db"
        initialize_database(self.path)
        record_attempt("TEST", "Q001", "D", 1, 1.25, database_path=self.path)

    def legacy_snapshot(self):
        with closing(get_connection(self.path, read_only=True)) as connection:
            return [[tuple(row) for row in connection.execute("SELECT * FROM " + table + " ORDER BY id")]
                    for table in ("questions", "attempts", "knowledge_points")]

    def test_reviewed_and_draft_are_rejected_without_database_writes(self):
        before = self.path.read_bytes()
        result = import_questions([candidate(), candidate(id="DRAFT", quality_status="draft")], database_path=self.path)
        self.assertEqual(result["rejected"], 2)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_approved_import_preserves_legacy_questions_attempts_and_answers(self):
        before = self.legacy_snapshot()
        mastery = calculate_student_mastery("TEST", database_path=self.path)
        recommendation = generate_recommendation("TEST", database_path=self.path)
        result = import_questions([approved()], database_path=self.path)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(self.legacy_snapshot(), before)
        self.assertEqual(calculate_student_mastery("TEST", database_path=self.path), mastery)
        self.assertEqual(generate_recommendation("TEST", database_path=self.path), recommendation)
        self.assertIn("本次学习表现", build_rule_based_feedback(build_feedback_context("TEST", database_path=self.path)))
        self.assertEqual(get_approved_questions("K002", database_path=self.path)[0]["quality_status"], "approved")

    def test_fingerprint_dedup_and_repeated_import(self):
        result = import_questions([approved(), approved(id="COPY", source_file="copy.docx")], database_path=self.path)
        self.assertEqual((result["inserted"], result["skipped"]), (1, 1))
        self.assertEqual(import_questions([approved()], database_path=self.path)["skipped"], 1)
        self.assertEqual(len(get_approved_questions("K002", database_path=self.path)), 1)

    def test_conflicting_id_rolls_back_entire_batch(self):
        result = import_questions([approved(), approved(stem="函数 f(x)=3x+1，求 f(2) 的值。")], database_path=self.path)
        self.assertEqual(result["inserted"], 0)
        self.assertTrue(result["errors"])
        self.assertEqual(get_approved_questions("K002", database_path=self.path), [])

    def test_suspicious_approved_candidate_is_rejected(self):
        result = import_questions([approved(stem="函数 f(x)=")], database_path=self.path)
        self.assertEqual(result["rejected"], 1)

    def test_real_database_path_is_refused(self):
        with self.assertRaisesRegex(ValueError, "真实"):
            import_questions([approved()], database_path=DATABASE_PATH)

    def test_new_k005_is_isolated_from_old_parameter_topic(self):
        result = import_questions([approved(primary_knowledge_point_id="K005")], database_path=self.path)
        self.assertEqual(result["inserted"], 1)
        with closing(get_connection(self.path, read_only=True)) as connection:
            self.assertEqual(connection.execute("SELECT name FROM knowledge_points WHERE id='K005'").fetchone()[0], "含参数函数")
            self.assertEqual(connection.execute("SELECT name FROM bank_knowledge_points WHERE id='K005'").fetchone()[0], "函数奇偶性")

    def test_recommendation_read_adapter_returns_only_approved_bank_items(self):
        import_questions([approved(), candidate(id="UNREVIEWED")], database_path=self.path)
        def bank_reader(key, *, database_path):
            return [{"id": row["id"], "stem": row["stem"], "difficulty": row["difficulty"],
                     "knowledge_point_id": row["primary_knowledge_point_id"], "knowledge_point_name": "函数表示"}
                    for row in get_approved_questions(key, database_path=database_path)]
        # Exercise the approved-only boundary without activating the real v2 migration.
        with patch("services.recommendation.get_questions_for_knowledge", side_effect=bank_reader):
            questions = recommend_questions("TEST", "K002", database_path=self.path)
        self.assertEqual([question["id"] for question in questions], ["TEST-Q1"])
