"""Database and Streamlit interaction tests using isolated seed databases."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from database.database import get_connection, get_training_questions
from init_db import initialize_database


class TrainingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)
        self.connection = get_connection(self.path)
        self.addCleanup(self.connection.close)

    def test_read_questions_and_parse_options(self) -> None:
        questions = get_training_questions(self.path)
        self.assertEqual(len(questions), 6)
        self.assertEqual([q["id"] for q in questions], [f"Q00{i}" for i in range(1, 7)])
        for question in questions:
            self.assertEqual(set(question["options"]), {"A", "B", "C", "D"})
            self.assertIn(question["answer"], question["options"])
            point = self.connection.execute("SELECT name FROM knowledge_points WHERE id = ?",
                                            (question["knowledge_point_id"],)).fetchone()
            self.assertEqual(question["knowledge_point_name"], point["name"])

    def test_invalid_json_and_options_are_rejected(self) -> None:
        for options in ("invalid", json.dumps({"A": "only one"}),
                        json.dumps({key: "" for key in "ABCD"})):
            with self.subTest(options=options):
                self.connection.execute("UPDATE questions SET options = ? WHERE id = 'Q001'", (options,))
                self.connection.commit()
                with self.assertRaises(ValueError):
                    get_training_questions(self.path)

    def test_missing_database_is_not_created(self) -> None:
        missing = self.path.parent / "missing.db"
        with self.assertRaises(FileNotFoundError):
            get_training_questions(missing)
        self.assertFalse(missing.exists())

    def test_only_function_questions_are_returned(self) -> None:
        self.connection.execute("UPDATE knowledge_points SET topic = '其他' WHERE id = 'K001'")
        self.connection.commit()
        self.assertEqual(len(get_training_questions(self.path)), 5)

    def test_training_submission_navigation_and_no_attempt_writes(self) -> None:
        original = get_training_questions
        with patch("database.database.get_training_questions", side_effect=lambda: original(self.path)):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
            self.assertEqual(len(app.exception), 0)
            self.assertIsNone(app.radio[0].value)
            app.button[0].click().run()
            self.assertEqual(app.warning[0].value, "请选择一个答案后再提交。")
            self.assertFalse(app.session_state["submitted"])
            app.radio[0].set_value("D").run()
            app.button[0].click().run()
            self.assertEqual(app.success[0].value, "回答正确")
            self.assertTrue(app.radio[0].disabled)
            app.run()
            self.assertEqual(app.success[0].value, "回答正确")
            app.button[1].click().run()
            self.assertEqual(app.session_state["question_index"], 1)
            self.assertIsNone(app.radio[0].value)
            self.assertFalse(app.session_state["submitted"])
            self.assertIsNone(app.session_state["feedback"])
            self.assertEqual(len(app.success), 0)
            app.radio[0].set_value("A").run()
            app.button[0].click().run()
            self.assertEqual(app.error[0].value, "回答错误")
            self.assertTrue(any("正确答案：B." in text.value for text in app.text))
            for _ in range(5):
                app.button[1].click().run()
            self.assertEqual(app.session_state["question_index"], 0)
            self.assertIsNone(app.radio[0].value)
            self.assertIsNone(app.session_state["feedback"])
            self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 0)

    def test_empty_database_shows_chinese_message(self) -> None:
        with patch("database.database.get_training_questions", return_value=[]):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("暂无函数专题选择题", app.info[0].value)


if __name__ == "__main__":
    unittest.main()
