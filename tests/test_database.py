"""Offline integration tests for the V0.1 SQLite foundation."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.database import DATABASE_PATH, get_connection
from init_db import initialize_database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "test.db"
        initialize_database(self.path)
        self.connection = get_connection(self.path)
        self.addCleanup(self.connection.close)

    def test_database_and_connection_configuration(self) -> None:
        self.assertTrue(self.path.is_file())
        self.assertEqual(DATABASE_PATH, Path(__file__).resolve().parents[1] / "math_ai.db")
        self.assertEqual(self.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertIs(self.connection.row_factory, sqlite3.Row)
        tables = {row["name"] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertTrue({"knowledge_points", "questions", "attempts"} <= tables)

    def test_knowledge_points_and_prerequisites(self) -> None:
        rows = self.connection.execute("SELECT * FROM knowledge_points ORDER BY id").fetchall()
        self.assertEqual([row["id"] for row in rows], [f"K00{i}" for i in range(1, 6)])
        self.assertEqual([row["name"] for row in rows],
                         ["函数概念", "定义域", "函数单调性", "函数最值", "含参数函数"])
        expected = [[], ["K001"], ["K001", "K002"], ["K002", "K003"], ["K003", "K004"]]
        self.assertEqual([json.loads(row["prerequisite_ids"]) for row in rows], expected)

    def test_questions_cover_all_points_and_difficulties(self) -> None:
        rows = self.connection.execute("SELECT * FROM questions ORDER BY id").fetchall()
        self.assertEqual(len(rows), 6)
        self.assertEqual({row["knowledge_point_id"] for row in rows},
                         {f"K00{i}" for i in range(1, 6)})
        self.assertEqual({row["difficulty"] for row in rows}, {1, 2, 3, 4, 5})
        self.assertEqual([row["answer"] for row in rows], ["D", "B", "A", "C", "B", "C"])
        for row in rows:
            self.assertEqual(set(json.loads(row["options"])), {"A", "B", "C", "D"})

    def insert_attempt(self, question_id: str = "Q001") -> int:
        cursor = self.connection.execute(
            """INSERT INTO attempts
               (student_id, question_id, user_answer, is_correct, answer_time, error_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("test_student", question_id, "A", 0, 42.5, "K"),
        )
        return cursor.lastrowid

    def test_attempt_insertion_and_query(self) -> None:
        attempt_id = self.insert_attempt()
        row = self.connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        self.assertEqual(row["student_id"], "test_student")
        self.assertEqual(row["answer_time"], 42.5)
        self.assertEqual(row["hint_count"], 0)
        self.assertEqual(row["retry_count"], 0)
        self.assertEqual(row["error_type"], "K")
        self.assertTrue(row["created_at"].endswith("Z"))

    def test_foreign_keys_reject_invalid_references(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_attempt("missing_question")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "UPDATE questions SET knowledge_point_id = 'missing' WHERE id = 'Q001'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "UPDATE knowledge_points SET parent_id = 'missing' WHERE id = 'K001'"
            )
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_reinitialization_preserves_seeds_and_attempts(self) -> None:
        self.insert_attempt()
        self.connection.execute("UPDATE questions SET explanation = '保留已有内容' WHERE id = 'Q001'")
        self.connection.commit()
        before = {table: [tuple(row) for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY id")]
                  for table in ("knowledge_points", "questions", "attempts")}
        initialize_database(self.path)
        initialize_database(self.path)
        after = {table: [tuple(row) for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY id")]
                 for table in before}
        self.assertEqual(before, after)

    def test_attempt_constraints(self) -> None:
        attempt_id = self.insert_attempt()
        for column, value in [("answer_time", -1), ("hint_count", -1), ("retry_count", -1),
                              ("is_correct", 2), ("error_type", "X"), ("user_answer", "E")]:
            with self.subTest(column=column), self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(f"UPDATE attempts SET {column} = ? WHERE id = ?", (value, attempt_id))


if __name__ == "__main__":
    unittest.main()
