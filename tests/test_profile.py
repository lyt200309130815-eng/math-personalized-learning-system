"""Profile formatting and page tests use temporary databases, without a browser."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from database.database import get_training_questions, record_attempt
from init_db import initialize_database
from services.mastery import calculate_student_mastery
from services.profile import build_profile_data, format_percentage


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)
        self.root = Path(__file__).resolve().parents[1]

    def data(self) -> dict:
        return build_profile_data(calculate_student_mastery("S001", database_path=self.path))

    def record(self, correct: int = 1) -> int:
        return record_attempt("S001", "Q001", "D" if correct else "A", correct,
                              2.5, database_path=self.path)

    def test_percentage_preserves_missing_and_measured_zero(self) -> None:
        self.assertEqual(format_percentage(None), "未评估")
        self.assertEqual(format_percentage(0), "0%")
        self.assertEqual(format_percentage(0.72), "72%")
        self.assertEqual(format_percentage(0.75), "75%")
        self.assertEqual(format_percentage(1), "100%")

    def test_all_unevaluated_points_and_empty_overview(self) -> None:
        profile = self.data()
        self.assertEqual([p["knowledge_point_id"] for p in profile["points"]], [f"K00{i}" for i in range(1, 6)])
        self.assertEqual(profile["chart"], [])
        self.assertEqual(len(profile["unevaluated"]), 5)
        self.assertEqual(profile["overview"]["overall_accuracy_display"], "暂无数据")
        self.assertEqual(profile["overview"]["total_attempts"], 0)
        for point in profile["points"]:
            self.assertEqual(point["mastery_display"], "未评估")
            self.assertEqual(point["mastery_level"], "未评估")
            self.assertEqual(point["evidence_level"], "无数据")
            self.assertEqual(point["attempt_count"], 0)

    def test_mixed_profile_retains_service_metrics_and_evidence(self) -> None:
        self.record()
        results = calculate_student_mastery("S001", database_path=self.path)
        profile = build_profile_data(results)
        for source, point in zip(results, profile["points"]):
            for key, value in source.items():
                self.assertEqual(point[key], value)
        point = profile["points"][0]
        self.assertEqual(point["mastery_display"], "100%")
        self.assertEqual(point["mastery_level"], "稳定掌握")
        self.assertEqual(point["attempt_count"], 1)
        self.assertEqual(point["correct_count"], 1)
        self.assertEqual(point["evidence_level"], "数据较少")
        self.assertIn("训练数据较少", point["evidence_note"])
        self.assertEqual(len(profile["chart"]), 1)
        self.assertEqual(profile["chart"][0]["掌握度（%）"], 100)
        self.assertEqual(profile["overview"]["trained_count"], 1)
        self.assertEqual(profile["overview"]["unevaluated_count"], 4)

    def test_overall_accuracy_is_weighted_by_attempt_count(self) -> None:
        self.record(1)
        self.record(0)
        record_attempt("S001", "Q002", "B", 1, 1, database_path=self.path)
        overview = self.data()["overview"]
        self.assertEqual(overview["total_attempts"], 3)
        self.assertEqual(overview["overall_accuracy_display"], "67%")

    def test_measured_zero_is_in_chart(self) -> None:
        self.record(0)
        profile = self.data()
        self.assertEqual(profile["points"][0]["mastery_display"], "0%")
        self.assertEqual(profile["chart"][0]["掌握度（%）"], 0)
        self.assertEqual(len(profile["unevaluated"]), 4)

    def test_profile_page_reads_latest_data_and_handles_no_attempts(self) -> None:
        original = calculate_student_mastery
        with patch("services.mastery.calculate_student_mastery",
                   side_effect=lambda student: original(student, database_path=self.path)) as reader:
            app = AppTest.from_file(str(self.root / "pages" / "profile.py")).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.info[0].value, "暂无训练数据")
            self.assertEqual(len(app.expander), 5)
            self.assertEqual(app.metric[3].value, "暂无数据")
            self.record()
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[2].value, "1 次")
            self.assertEqual(app.metric[3].value, "100%")
            self.assertEqual(reader.call_count, 2)

    def test_database_error_is_friendly(self) -> None:
        with patch("services.mastery.calculate_student_mastery", side_effect=sqlite3.OperationalError("private error")):
            app = AppTest.from_file(str(self.root / "pages" / "profile.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("知识画像读取失败", app.error[0].value)
        self.assertNotIn("private error", app.error[0].value)

    def test_chart_has_fixed_percentage_domain_and_no_unevaluated_values(self) -> None:
        self.record()
        profile = self.data()
        spec = profile["chart_spec"]
        self.assertEqual(spec["encoding"]["x"]["scale"]["domain"], [0, 100])
        self.assertEqual(spec["data"]["values"], profile["chart"])
        self.assertEqual(len(spec["data"]["values"]), 1)
        self.assertNotIn("K002", str(spec["data"]["values"]))

    def test_all_wrong_overview_is_zero_not_missing(self) -> None:
        self.record(0)
        self.assertEqual(self.data()["overview"]["overall_accuracy_display"], "0%")

    def test_page_displays_correct_count_and_percentage_chart(self) -> None:
        self.record()
        original = calculate_student_mastery
        with patch("services.mastery.calculate_student_mastery",
                   side_effect=lambda student: original(student, database_path=self.path)):
            app = AppTest.from_file(str(self.root / "pages" / "profile.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("正确次数：1" in item.value for item in app.markdown))
        self.assertTrue(any("以下知识点尚未评估" in item.value for item in app.markdown))
        self.assertEqual(len(app.get("arrow_vega_lite_chart")), 1)

    def test_navigation_preserves_training_and_opens_profile(self) -> None:
        original_questions = get_training_questions
        original_mastery = calculate_student_mastery
        with patch("database.database.get_training_questions", side_effect=lambda: original_questions(self.path)), \
                patch("services.mastery.calculate_student_mastery", side_effect=lambda student: original_mastery(student, database_path=self.path)):
            app = AppTest.from_file(str(self.root / "app.py")).run()
            app.radio[0].set_value("D").run()
            started_at = app.session_state["question_started_at"]
            app.switch_page("pages/profile.py").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.header[0].value, "知识画像")
            app.switch_page("pages/training.py").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.radio[0].value, "D")
            self.assertEqual(app.session_state["question_started_at"], started_at)


if __name__ == "__main__":
    unittest.main()
