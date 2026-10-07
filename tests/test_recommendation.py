"""Recommendation rules tested with temporary SQLite and controlled mastery fixtures."""

import json
import sqlite3
import tempfile
import unittest
from runtime_helpers import use_v1_test_config
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from database.database import get_connection, get_function_knowledge_points, get_training_questions, record_attempt
from init_db import initialize_database
from services.mastery import calculate_student_mastery, get_mastery_level
from services.recommendation import (
    generate_recommendation, get_difficulty_range, get_recommendation_type,
    recommend_next_knowledge, recommend_questions,
)


class RecommendationTests(unittest.TestCase):
    def setUp(self) -> None:
        use_v1_test_config(self)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)

    def fixture(self, scores=None, evidence="数据较充分") -> list[dict]:
        results = calculate_student_mastery("S001", database_path=self.path)
        for result, score in zip(results, scores or [0.9] * 5):
            result.update(mastery_score=score, mastery_level=get_mastery_level(score),
                          attempt_count=0 if score is None else 6,
                          evidence_level="无数据" if score is None else evidence)
        return results

    def target(self, scores, evidence="数据较充分") -> dict:
        with patch("services.recommendation.calculate_student_mastery", return_value=self.fixture(scores, evidence)):
            return recommend_next_knowledge("S001", database_path=self.path)

    def add_question(self, key: str, difficulty: int = 2) -> None:
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute(
                    """INSERT INTO questions
                       SELECT ?, stem, options, answer, explanation, knowledge_point_id,
                              ?, ability_tag, question_type, estimated_time
                       FROM questions WHERE id = ?""", (key, difficulty, "Q001"),
                )

    def test_no_data_starts_with_k001_diagnosis(self) -> None:
        result = generate_recommendation("S001", database_path=self.path)
        target = result["target_knowledge"]
        self.assertEqual(target["knowledge_point_id"], "K001")
        self.assertEqual(target["recommendation_type"], "诊断")
        self.assertEqual(target["difficulty_range"], [1, 2])
        self.assertIn("当前暂无训练数据", target["reason"])

    def test_weak_advanced_point_falls_back_to_k004(self) -> None:
        result = self.target([0.9, 0.9, 0.9, 0.45, 0.30])
        self.assertEqual(result["knowledge_point_id"], "K004")
        self.assertIn("前置知识", result["reason"])
        self.assertIn("含参数函数", result["reason"])

    def test_multilevel_prerequisite_fallback(self) -> None:
        result = self.target([0.9, 0.45, 0.5, 0.4, 0.2])
        self.assertEqual(result["knowledge_point_id"], "K002")

    def test_weak_ancestor_is_checked_even_when_direct_parents_pass(self) -> None:
        self.assertEqual(self.target([0.9, 0.45, 0.9, 0.9, 0.2])["knowledge_point_id"], "K002")

    def test_unassessed_prerequisite_is_diagnosed_first(self) -> None:
        self.assertEqual(self.target([None, 0.9, 0.9, 0.9, 0.2])["knowledge_point_id"], "K001")

    def test_prerequisites_at_threshold_allow_advanced_target(self) -> None:
        self.assertEqual(self.target([0.9, 0.9, 0.60, 0.60, 0.30])["knowledge_point_id"], "K005")

    def test_strategy_and_difficulty_boundaries(self) -> None:
        cases = [(None, "无数据", "诊断", (1, 2)), (0.39, "数据较充分", "补弱", (1, 2)),
                 (0.40, "数据较充分", "补弱", (2, 3)), (0.59, "初步判断", "补弱", (2, 3)),
                 (0.60, "数据较充分", "巩固", (3, 4)), (0.79, "初步判断", "巩固", (3, 4)),
                 (0.80, "数据较少", "验证", (2, 3)), (1.0, "初步判断", "验证", (2, 3)),
                 (0.80, "数据较充分", "提升", (4, 5))]
        for score, evidence, strategy, band in cases:
            with self.subTest(score=score, evidence=evidence):
                mastery = {"mastery_score": score, "evidence_level": evidence}
                self.assertEqual(get_recommendation_type(mastery), strategy)
                self.assertEqual(get_difficulty_range(mastery), band)
                self.assertEqual(mastery["mastery_score"], score)

    def test_all_high_scores_low_evidence_get_verification(self) -> None:
        result = self.target([1] * 5, "数据较少")
        self.assertEqual(result["recommendation_type"], "验证")
        self.assertEqual(result["difficulty_range"], [2, 3])

    def test_all_mastered_get_improvement_at_deepest_point(self) -> None:
        result = self.target([0.9, 0.88, 0.9, 0.95, 0.99])
        self.assertEqual(result["knowledge_point_id"], "K005")
        self.assertEqual(result["recommendation_type"], "提升")
        self.assertEqual(result["difficulty_range"], [4, 5])

    def test_improvement_depth_follows_changed_database_graph(self) -> None:
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?", ("[]", "K005"))
        self.assertEqual(self.target([1] * 5)["knowledge_point_id"], "K004")

    def test_improvement_same_depth_uses_score_count_then_id(self) -> None:
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?",
                                   ('["K003"]', "K005"))
        for score4, score5, count4, count5, expected in (
                (0.95, 0.85, 6, 6, "K005"), (0.90, 0.90, 8, 6, "K005"),
                (0.90, 0.90, 6, 6, "K004")):
            results = self.fixture()
            results[3].update(mastery_score=score4, attempt_count=count4)
            results[4].update(mastery_score=score5, attempt_count=count5)
            with self.subTest(expected=expected), patch(
                    "services.recommendation.calculate_student_mastery", return_value=results):
                self.assertEqual(recommend_next_knowledge("S001", database_path=self.path)["knowledge_point_id"], expected)

    def test_verification_prefers_evidence_then_count_then_id(self) -> None:
        results = self.fixture([0.81, 1, 1, 1, 1], "初步判断")
        results[4].update(evidence_level="数据较少", attempt_count=2)
        with patch("services.recommendation.calculate_student_mastery", return_value=results):
            self.assertEqual(recommend_next_knowledge("S001", database_path=self.path)["knowledge_point_id"], "K005")
        results[3].update(evidence_level="数据较少", attempt_count=1)
        with patch("services.recommendation.calculate_student_mastery", return_value=results):
            self.assertEqual(recommend_next_knowledge("S001", database_path=self.path)["knowledge_point_id"], "K004")
        results[4].update(attempt_count=1)
        with patch("services.recommendation.calculate_student_mastery", return_value=list(reversed(results))):
            self.assertEqual(recommend_next_knowledge("S001", database_path=self.path)["knowledge_point_id"], "K004")

    def test_database_prerequisites_are_used_instead_of_hardcoded_graph(self) -> None:
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?",
                                   (json.dumps(["K002"]), "K005"))
        result = self.target([0.9, 0.5, 0.9, 0.9, 0.2])
        self.assertEqual(result["knowledge_point_id"], "K002")

    def test_invalid_and_cyclic_prerequisites_fail_cleanly(self) -> None:
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?",
                                   (json.dumps(["missing"]), "K001"))
        with self.assertRaises(ValueError):
            self.target([0.2] * 5)
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?",
                                   (json.dumps(["K002"]), "K001"))
        with self.assertRaises(ValueError):
            self.target([0.2] * 5)

    def test_recent_questions_are_deprioritized_and_old_questions_fill(self) -> None:
        self.add_question("Q101")
        self.add_question("Q102")
        record_attempt("S001", "Q001", "D", 1, 1, database_path=self.path)
        questions = recommend_questions("S001", "K001", database_path=self.path)
        self.assertEqual([q["id"] for q in questions], ["Q101", "Q102", "Q001"])
        self.assertFalse(questions[0]["recently_practiced"])
        self.assertTrue(questions[-1]["recently_practiced"])
        self.assertEqual(len({q["id"] for q in questions}), len(questions))
        self.assertEqual(len(recommend_questions("S001", "K001", 1, database_path=self.path)), 1)

    def test_recent_window_only_uses_ten_attempts(self) -> None:
        self.add_question("Q101")
        record_attempt("S001", "Q001", "D", 1, 1, database_path=self.path)
        for _ in range(10):
            record_attempt("S001", "Q101", "D", 1, 1, database_path=self.path)
        questions = recommend_questions("S001", "K001", database_path=self.path)
        self.assertEqual(questions[0]["id"], "Q001")
        self.assertFalse(questions[0]["recently_practiced"])

    def test_preferred_difficulty_orders_fresh_questions_first(self) -> None:
        self.add_question("Q101", 5)
        self.add_question("Q102", 2)
        questions = recommend_questions("S001", "K001", database_path=self.path)
        self.assertEqual([q["id"] for q in questions], ["Q001", "Q102", "Q101"])
        self.assertTrue(questions[-1]["difficulty_fallback"])

    def test_insufficient_questions_fallback_and_empty_pool(self) -> None:
        questions = recommend_questions("S001", "K005", database_path=self.path)
        self.assertEqual(len(questions), 2)
        self.assertTrue(all(q["difficulty_fallback"] for q in questions))
        with closing(get_connection(self.path)) as connection:
            with connection:
                connection.execute("DELETE FROM questions WHERE knowledge_point_id = ?", ("K005",))
        self.assertEqual(recommend_questions("S001", "K005", database_path=self.path), [])

    def test_limits_structure_reasons_and_readonly(self) -> None:
        before = self.path.read_bytes()
        result = generate_recommendation("S001", database_path=self.path)
        self.assertEqual(set(result), {"student_id", "target_knowledge", "recommended_questions"})
        self.assertTrue(result["target_knowledge"]["reason"])
        self.assertEqual(result["student_id"], "S001")
        self.assertNotIn("answer", result["recommended_questions"][0])
        self.assertEqual(generate_recommendation("S001", 0, database_path=self.path)["recommended_questions"], [])
        for limit in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                generate_recommendation("S001", limit, database_path=self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_recommendation_page_navigation_and_friendly_error(self) -> None:
        original = generate_recommendation
        root = Path(__file__).resolve().parents[1]
        with patch("services.recommendation.generate_recommendation",
                   side_effect=lambda student: original(student, database_path=self.path)):
            app = AppTest.from_file(str(root / "pages" / "recommendation.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "个性化训练推荐")
        self.assertIn("函数概念", app.subheader[0].value)
        with patch("services.recommendation.generate_recommendation", side_effect=sqlite3.OperationalError("private")):
            app = AppTest.from_file(str(root / "pages" / "recommendation.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("推荐数据读取失败", app.error[0].value)
        self.assertNotIn("private", app.error[0].value)

    def test_navigation_opens_recommendation_and_returns_to_training(self) -> None:
        original = generate_recommendation
        root = Path(__file__).resolve().parents[1]
        with patch("database.database.get_training_questions", side_effect=lambda: get_training_questions(self.path)), \
                patch("services.recommendation.generate_recommendation",
                      side_effect=lambda student: original(student, database_path=self.path)):
            app = AppTest.from_file(str(root / "app.py")).run()
            app.switch_page("pages/recommendation.py").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.title[0].value, "个性化训练推荐")
            app.switch_page("pages/training.py").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.radio), 1)


def run_acceptance_scenarios(database_path: Path) -> list[dict]:
    """Build eight real-history scenarios exclusively in a caller's temporary database."""
    initialize_database(database_path)
    points = get_function_knowledge_points(database_path=database_path)
    graph = {point["id"]: json.loads(point["prerequisite_ids"]) for point in points}
    with closing(get_connection(database_path)) as connection:
        with connection:
            for point in points:
                source = connection.execute("SELECT id FROM questions WHERE knowledge_point_id = ? ORDER BY id",
                                            (point["id"],)).fetchone()[0]
                for difficulty in range(1, 6):
                    for copy in range(1, 4):
                        suffix = "" if copy == 1 else f"_{copy}"
                        connection.execute(
                            """INSERT INTO questions
                               SELECT ?, stem, options, answer, explanation, knowledge_point_id,
                                      ?, ability_tag, question_type, estimated_time FROM questions WHERE id = ?""",
                            (f"TEST_{point['id']}_D{difficulty}{suffix}", difficulty, source),
                        )
            for index in range(101, 106):
                connection.execute(
                    """INSERT INTO questions
                       SELECT ?, stem, options, answer, explanation, knowledge_point_id,
                              3, ability_tag, question_type, estimated_time FROM questions WHERE id = ?""",
                    (f"Q{index}", "Q003"),
                )

    full = [1] * 6
    weak = [0, 0, 0, 0, 0, 1]
    insufficient = [1, 0, 1, 0, 1, 0]
    medium = [0, 1, 1, 1, 0, 1]
    configurations = [
        ("TEST_NO_DATA", {}, "K001", "诊断", [1, 2]),
        ("TEST_BASIC_WEAK", {"K001": weak}, "K001", "补弱", [1, 2]),
        ("TEST_PARAMETER_WITH_WEAK_PREREQ", dict(zip(
            [p["id"] for p in points], [full, full, insufficient, medium, [0] * 6])), "K003", "补弱", [2, 3]),
        ("TEST_MULTI_LEVEL_FALLBACK", dict(zip(
            [p["id"] for p in points], [full, weak, insufficient, insufficient, [0] * 6])), "K002", "补弱", [1, 2]),
        ("TEST_HIGH_LOW_EVIDENCE", {p["id"]: [1] for p in points}, "K001", "验证", [2, 3]),
        ("TEST_ALL_MASTERED", {p["id"]: full for p in points}, "K005", "提升", [4, 5]),
        ("TEST_RECENT_DUPLICATE", {}, "K003", "巩固", [3, 4]),
        ("TEST_MEDIUM", dict(zip(
            [p["id"] for p in points], [full, full, medium, full, full])), "K003", "巩固", [3, 4]),
    ]

    def insert_history(student: str, point: str, history: list[int]) -> None:
        with closing(get_connection(database_path)) as connection:
            question = connection.execute("SELECT id, answer FROM questions WHERE knowledge_point_id = ? ORDER BY id",
                                          (point,)).fetchone()
        for index, correct in enumerate(history):
            wrong = "B" if question["answer"] == "A" else "A"
            attempt_id = record_attempt(student, question["id"], question["answer"] if correct else wrong,
                                        correct, 2.5, database_path=database_path)
            with closing(get_connection(database_path)) as connection:
                with connection:
                    connection.execute("UPDATE attempts SET created_at = ? WHERE id = ?",
                                       (f"2026-01-{index + 1:02d}T00:00:00.000Z", attempt_id))

    reports = []
    for student, histories, expected_id, expected_type, expected_band in configurations:
        for point, history in histories.items():
            insert_history(student, point, history)
        if student == "TEST_RECENT_DUPLICATE":
            for point in points:
                if point["id"] != "K003":
                    insert_history(student, point["id"], full)
            # A=2/3, recent R=.8, M≈.665: consolidation, Q101/Q102 recently seen.
            for index, correct in enumerate(medium):
                record_attempt(student, "Q101" if index % 2 == 0 else "Q102", "A" if correct else "B",
                               correct, 2.5, database_path=database_path)
        mastery = calculate_student_mastery(student, database_path=database_path)
        result = generate_recommendation(student, database_path=database_path)
        target = result["target_knowledge"]
        target_id = target["knowledge_point_id"]
        by_id = {row["knowledge_point_id"]: row for row in mastery}

        def prerequisite_paths(start: str, end: str) -> list[list[str]]:
            if start == end:
                return [[end]]
            return [[start] + path for parent in graph[start]
                    for path in prerequisite_paths(parent, end)]

        paths = prerequisite_paths("K005", target_id)
        ancestor_checks = {}

        def inspect_ancestors(key: str) -> None:
            for parent in graph[key]:
                if parent not in ancestor_checks:
                    score = by_id[parent]["mastery_score"]
                    ancestor_checks[parent] = score is not None and score >= 0.60
                    inspect_ancestors(parent)

        inspect_ancestors(target_id)
        questions = result["recommended_questions"]
        if student == "TEST_RECENT_DUPLICATE":
            questions = recommend_questions(student, "K003", database_path=database_path)
        passed = (target_id == expected_id and target["recommendation_type"] == expected_type
                  and target["difficulty_range"] == expected_band and bool(target["reason"])
                  and bool(questions) and all(ancestor_checks.values())
                  and len({q["id"] for q in questions}) == len(questions)
                  and all(expected_band[0] <= q["difficulty"] <= expected_band[1] for q in questions))
        if student == "TEST_RECENT_DUPLICATE":
            flags = [q["recently_practiced"] for q in questions]
            passed = passed and flags == sorted(flags) and all(
                any(q["id"] == key for q in questions) for key in ("Q103", "Q104", "Q105"))
        reports.append({
            "student_id": student,
            "mastery": {key: {field: row[field] for field in ("mastery_score", "attempt_count", "evidence_level")}
                        for key, row in by_id.items()},
            "prerequisite_graph": graph, "fallback_paths_from_k005": paths,
            "target_ancestor_checks": ancestor_checks, "target_knowledge_id": target_id,
            "recommendation_type": target["recommendation_type"], "reason": target["reason"],
            "difficulty_range": target["difficulty_range"],
            "question_ids": [q["id"] for q in questions],
            "actual_difficulties": [q["difficulty"] for q in questions],
            "result": "PASS" if passed else "FAIL",
        })
    return reports


class RecommendationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        use_v1_test_config(self)

    def test_eight_real_history_acceptance_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reports = run_acceptance_scenarios(Path(directory) / "acceptance.db")
        for report in reports:
            with self.subTest(student=report["student_id"]):
                self.assertEqual(report["result"], "PASS", json.dumps(report, ensure_ascii=False))
        by_student = {r["student_id"]: r for r in reports}
        weak = by_student["TEST_PARAMETER_WITH_WEAK_PREREQ"]["mastery"]
        self.assertTrue(0.40 <= weak["K003"]["mastery_score"] <= 0.55)
        self.assertGreaterEqual(weak["K004"]["mastery_score"], 0.65)
        self.assertLess(weak["K005"]["mastery_score"], 0.40)
        self.assertIsNone(by_student["TEST_NO_DATA"]["mastery"]["K001"]["mastery_score"])

    def test_tie_break_is_stable_under_reversed_query_and_prerequisite_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tie.db"
            initialize_database(path)
            results = calculate_student_mastery("TEST_TIE", database_path=path)
            for row in results:
                row.update(mastery_score=1.0, attempt_count=6, evidence_level="数据较充分")
            for ordering in (results, list(reversed(results))):
                with patch("services.recommendation.calculate_student_mastery", return_value=ordering):
                    outputs = [generate_recommendation("TEST_TIE", database_path=path) for _ in range(5)]
                self.assertTrue(all(result == outputs[0] for result in outputs))
                self.assertEqual(outputs[0]["target_knowledge"]["knowledge_point_id"], "K005")
            # Equal unmet candidates flow through a set; the final ID tie-break remains stable.
            for row in results:
                row.update(mastery_score=0.45 if row["knowledge_point_id"] in ("K003", "K004") else
                           0.1 if row["knowledge_point_id"] == "K005" else 1.0)
            with closing(get_connection(path)) as connection:
                with connection:
                    connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?",
                                       ("[]", "K004"))
            for parents in (["K003", "K004"], ["K004", "K003"]):
                with closing(get_connection(path)) as connection:
                    with connection:
                        connection.execute("UPDATE knowledge_points SET prerequisite_ids = ? WHERE id = ?",
                                           (json.dumps(parents), "K005"))
                with patch("services.recommendation.calculate_student_mastery", return_value=results):
                    target = recommend_next_knowledge("TEST_TIE", database_path=path)
                self.assertEqual(target["knowledge_point_id"], "K003")


if __name__ == "__main__":
    unittest.main()
