"""Offline persistence and training-state tests; no real browser is required."""

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from database.database import get_connection, get_recent_attempts, record_attempt
from init_db import initialize_database
from services.training import advance_question, initialize_training_state, submit_training_answer


class AttemptTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)

    def record(self, **kwargs) -> int:
        values = dict(student_id="S001", question_id="Q001", user_answer="D",
                      is_correct=1, answer_time=12.75)
        values.update(kwargs)
        return record_attempt(**values, database_path=self.path)

    def test_correct_and_incorrect_attempt_fields(self) -> None:
        for answer, correct in [("D", 1), ("A", 0)]:
            with self.subTest(answer=answer):
                attempt_id = self.record(user_answer=answer, is_correct=correct)
                row = get_recent_attempts("S001", database_path=self.path)[0]
                self.assertEqual(row["id"], attempt_id)
                self.assertEqual(row["student_id"], "S001")
                self.assertEqual(row["question_id"], "Q001")
                self.assertEqual(row["user_answer"], answer)
                self.assertEqual(row["is_correct"], correct)
                self.assertEqual(row["answer_time"], 12.75)
                self.assertEqual(row["hint_count"], 0)
                self.assertEqual(row["retry_count"], 0)
                self.assertIsNone(row["error_type"])
                self.assertIsNotNone(datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).tzinfo)

    def test_invalid_correctness_and_time_are_rejected(self) -> None:
        for value in (-1, 2, 0.5):
            with self.subTest(is_correct=value), self.assertRaises(ValueError):
                self.record(is_correct=value)
        for value in (-1, float("inf"), float("nan")):
            with self.subTest(answer_time=value), self.assertRaises(ValueError):
                self.record(answer_time=value)
        self.assertEqual(get_recent_attempts("S001", database_path=self.path), [])

    def test_foreign_key_rejects_unknown_question(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.record(question_id="missing")
        self.assertEqual(get_recent_attempts("S001", database_path=self.path), [])

    def test_recent_attempts_filter_order_limit_and_parameters(self) -> None:
        ids = [self.record() for _ in range(12)]
        self.record(student_id="S002")
        rows = get_recent_attempts("S001", database_path=self.path)
        self.assertEqual([r["id"] for r in rows], list(reversed(ids))[:10])
        self.assertEqual(len(get_recent_attempts("S001", 2, database_path=self.path)), 2)
        self.assertEqual(get_recent_attempts("S001", 0, database_path=self.path), [])
        self.assertEqual(get_recent_attempts("' OR 1=1 --", database_path=self.path), [])
        for limit in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                get_recent_attempts("S001", limit, database_path=self.path)

    def test_timer_reruns_single_submission_and_next_question(self) -> None:
        state = {}
        initialize_training_state(state, now=100.0)
        initialize_training_state(state, now=105.0)
        self.assertEqual(state["question_started_at"], 100.0)
        recorder = Mock(side_effect=lambda **values: record_attempt(**values, database_path=self.path))
        submit_training_answer(state, "Q001", "D", now=106.0, recorder=recorder)
        recorder.assert_not_called()
        state["selected_answer"] = "D"
        submit_training_answer(state, "Q001", "D", now=112.75, recorder=recorder)
        attempt_id = state["recorded_attempt_id"]
        self.assertTrue(state["submitted"])
        self.assertEqual(state["feedback"], "回答正确")
        submit_training_answer(state, "Q001", "D", now=120.0, recorder=recorder)
        initialize_training_state(state, now=125.0)
        self.assertEqual(state["recorded_attempt_id"], attempt_id)
        self.assertEqual(recorder.call_count, 1)
        row = get_recent_attempts("S001", database_path=self.path)[0]
        self.assertEqual(row["answer_time"], 12.75)
        advance_question(state, 6, now=130.0)
        self.assertEqual(state["question_index"], 1)
        self.assertEqual(state["question_started_at"], 130.0)
        for key in ("selected_answer", "feedback", "recorded_attempt_id", "answer_time"):
            self.assertIsNone(state[key])
        self.assertFalse(state["submitted"])
        state["selected_answer"] = "A"
        submit_training_answer(state, "Q002", "B", now=134.5, recorder=recorder)
        row = get_recent_attempts("S001", database_path=self.path)[0]
        self.assertEqual((row["question_id"], row["is_correct"], row["answer_time"]), ("Q002", 0, 4.5))
        self.assertEqual(len(get_recent_attempts("S001", database_path=self.path)), 2)

    def test_failed_write_can_be_resubmitted_without_restarting_timer(self) -> None:
        state = {}
        initialize_training_state(state, now=100.0)
        state["selected_answer"] = "D"
        recorder = Mock(side_effect=[sqlite3.OperationalError("locked"), 7])
        with self.assertRaises(sqlite3.OperationalError):
            submit_training_answer(state, "Q001", "D", now=110.0, recorder=recorder)
        self.assertFalse(state["submitted"])
        self.assertIsNone(state["recorded_attempt_id"])
        submit_training_answer(state, "Q001", "D", now=120.0, recorder=recorder)
        self.assertEqual(state["recorded_attempt_id"], 7)
        self.assertEqual(recorder.call_args.kwargs["answer_time"], 10.0)


if __name__ == "__main__":
    unittest.main()
