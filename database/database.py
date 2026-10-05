"""Shared SQLite connection configuration."""

import sqlite3
import json
from contextlib import closing
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent.parent / "math_ai.db"


def get_connection(database_path: str | Path = DATABASE_PATH) -> sqlite3.Connection:
    """Open a connection with named rows and enforced foreign keys.

    The caller owns the connection and must close it after use.
    An alternative path allows tests to use isolated temporary databases.
    """
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_training_questions(database_path: str | Path = DATABASE_PATH) -> list[dict]:
    """Read function-topic questions, join knowledge names, and validate options."""
    if not Path(database_path).is_file():
        raise FileNotFoundError("数据库不存在，请先运行 python init_db.py。")
    with closing(get_connection(database_path)) as connection:
        rows = connection.execute(
            """SELECT q.*, k.name AS knowledge_point_name
               FROM questions AS q
               JOIN knowledge_points AS k ON k.id = q.knowledge_point_id
               WHERE k.topic = ? AND q.question_type = ? ORDER BY q.id""",
            ("函数", "single_choice"),
        ).fetchall()
    questions = []
    for row in rows:
        question = dict(row)
        try:
            options = json.loads(question["options"])
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError(f"题目 {question['id']} 的选项 JSON 无效。") from error
        if (not isinstance(options, dict) or set(options) != {"A", "B", "C", "D"}
                or any(not isinstance(value, str) or not value.strip() for value in options.values())
                or question["answer"] not in options):
            raise ValueError(f"题目 {question['id']} 的选项或答案无效。")
        question["options"] = options
        questions.append(question)
    return questions
