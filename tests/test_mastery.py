"""Mastery tests use temporary SQLite data exclusively."""

import math
import sqlite3
import tempfile
import unittest
from contextlib import closing
from itertools import product
from pathlib import Path

from database.database import get_connection, get_knowledge_attempts, record_attempt
from init_db import initialize_database
from services.mastery import (
    calculate_knowledge_mastery, calculate_student_mastery, get_evidence_level, get_mastery_level,
)


class MasteryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)

    def add_attempt(self, correct: int, question_id: str = "Q001", student_id: str = "S001",
                    created_at: str | None = None) -> int:
        answer = "D" if question_id == "Q001" else ("B" if question_id == "Q005" else "C")
        attempt_id = record_attempt(student_id, question_id, answer if correct else "A", correct,
                                    1.25, database_path=self.path)
        if created_at is not None:
            with closing(get_connection(self.path)) as connection:
                with connection:
                    connection.execute("UPDATE attempts SET created_at = ? WHERE id = ?",
                                       (created_at, attempt_id))
        return attempt_id

    def mastery(self, point: str = "K001", student: str = "S001") -> dict:
        return calculate_knowledge_mastery(student, point, database_path=self.path)

    def test_no_attempts_are_unevaluated(self) -> None:
        result = self.mastery()
        self.assertEqual(result["attempt_count"], 0)
        self.assertEqual(result["correct_count"], 0)
        for field in ("overall_accuracy", "recent_accuracy", "stability", "difficulty_performance", "mastery_score"):
            self.assertIsNone(result[field])
        self.assertEqual(result["mastery_level"], "未评估")
        self.assertEqual(result["evidence_level"], "无数据")

    def test_all_correct(self) -> None:
        for _ in range(7):
            self.add_attempt(1)
        result = self.mastery()
        for field in ("overall_accuracy", "recent_accuracy", "stability", "difficulty_performance", "mastery_score"):
            self.assertEqual(result[field], 1.0)
        self.assertEqual(result["mastery_level"], "稳定掌握")

    def test_all_incorrect(self) -> None:
        for _ in range(7):
            self.add_attempt(0)
        result = self.mastery()
        for field in ("overall_accuracy", "recent_accuracy", "stability", "difficulty_performance", "mastery_score"):
            self.assertEqual(result[field], 0.0)
        self.assertEqual(result["mastery_level"], "明显薄弱")

    def test_mixed_accuracy_stability_and_difficulty_weighting(self) -> None:
        for correct, question in [(1, "Q005"), (0, "Q006"), (1, "Q005"), (0, "Q006")]:
            self.add_attempt(correct, question)
        result = self.mastery("K005")
        self.assertEqual((result["attempt_count"], result["correct_count"]), (4, 2))
        self.assertEqual(result["overall_accuracy"], 0.5)
        self.assertEqual(result["recent_accuracy"], 0.5)
        self.assertEqual(result["stability"], 0.25)
        self.assertAlmostEqual(result["difficulty_performance"], 8 / 18)
        self.assertAlmostEqual(result["mastery_score"], 0.5 * 0.5 + 0.2 * 0.5 + 0.15 * 0.25 + 0.15 * 8 / 18)

    def test_population_standard_deviation(self) -> None:
        for correct in (1, 1, 1, 1, 0):
            self.add_attempt(correct)
        # Bernoulli population variance is p*(1-p)=0.16, std=0.4.
        self.assertAlmostEqual(self.mastery()["stability"], 0.8 * (1 - 0.4))

    def test_recent_five_use_timestamp_not_insertion_order(self) -> None:
        for day in range(2, 7):
            self.add_attempt(1, created_at=f"2026-01-{day:02d}T00:00:00.000Z")
        self.add_attempt(0, created_at="2026-01-01T00:00:00.000Z")
        result = self.mastery()
        self.assertEqual(result["recent_accuracy"], 1)
        self.assertEqual(result["stability"], 1)
        self.assertAlmostEqual(result["overall_accuracy"], 5 / 6)

    def test_timestamp_ties_use_newest_id(self) -> None:
        timestamp = "2026-01-01T00:00:00.000Z"
        ids = [self.add_attempt(correct, created_at=timestamp) for correct in (0, 1, 1, 1, 1, 1)]
        rows = get_knowledge_attempts("S001", "K001", database_path=self.path)
        self.assertEqual([row["id"] for row in rows], list(reversed(ids)))
        self.assertEqual(self.mastery()["recent_accuracy"], 1)

    def test_single_attempt_stability(self) -> None:
        self.add_attempt(1, student_id="correct_student")
        self.add_attempt(0, student_id="incorrect_student")
        self.assertEqual(self.mastery(student="correct_student")["stability"], 1)
        self.assertEqual(self.mastery(student="incorrect_student")["stability"], 0)

    def test_score_range_for_all_short_binary_histories(self) -> None:
        for length in range(1, 5):
            for index, history in enumerate(product((0, 1), repeat=length)):
                student = f"case_{length}_{index}"
                for correct in history:
                    self.add_attempt(correct, student_id=student)
                result = self.mastery(student=student)
                for field in ("overall_accuracy", "recent_accuracy", "stability", "difficulty_performance", "mastery_score"):
                    self.assertGreaterEqual(result[field], 0)
                    self.assertLessEqual(result[field], 1)

    def test_mastery_level_boundaries(self) -> None:
        for threshold, below, at in [(0.40, "明显薄弱", "基础不足"), (0.60, "基础不足", "基本掌握"),
                                     (0.80, "基本掌握", "熟练"), (0.90, "熟练", "稳定掌握")]:
            with self.subTest(threshold=threshold):
                self.assertEqual(get_mastery_level(math.nextafter(threshold, 0)), below)
                self.assertEqual(get_mastery_level(threshold), at)
        self.assertEqual(get_mastery_level(0), "明显薄弱")
        self.assertEqual(get_mastery_level(1), "稳定掌握")
        self.assertEqual(get_mastery_level(None), "未评估")

    def test_evidence_boundaries_and_no_score_effect(self) -> None:
        for count, expected in [(0, "无数据"), (1, "数据较少"), (2, "数据较少"),
                                (3, "初步判断"), (5, "初步判断"), (6, "数据较充分")]:
            self.assertEqual(get_evidence_level(count), expected)
        for _ in range(6):
            self.add_attempt(1)
            result = self.mastery()
            self.assertEqual(result["mastery_score"], 1)
            self.assertEqual(result["evidence_level"], get_evidence_level(result["attempt_count"]))

    def test_student_results_include_all_points_and_isolate_students(self) -> None:
        self.add_attempt(1)
        self.add_attempt(0, "Q005", student_id="other")
        results = calculate_student_mastery("S001", database_path=self.path)
        self.assertEqual([row["knowledge_point_id"] for row in results], [f"K00{i}" for i in range(1, 6)])
        self.assertEqual(results[0]["mastery_score"], 1)
        for row in results[1:]:
            self.assertIsNone(row["mastery_score"])
            self.assertEqual(row["mastery_level"], "未评估")
        self.assertEqual(self.mastery(student="' OR 1=1 --")["attempt_count"], 0)

    def test_read_only_calculation_preserves_database(self) -> None:
        self.add_attempt(1)
        original = self.path.read_bytes()
        calculate_student_mastery("S001", database_path=self.path)
        self.assertEqual(self.path.read_bytes(), original)
        with closing(get_connection(self.path, read_only=True)) as connection:
            with self.assertRaises(sqlite3.OperationalError) as raised:
                connection.execute("DELETE FROM attempts")
            self.assertIn("readonly", str(raised.exception))

    def test_unknown_point_and_missing_database(self) -> None:
        with self.assertRaises(ValueError):
            self.mastery("unknown")
        missing = self.path.parent / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            calculate_student_mastery("S001", database_path=missing)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
