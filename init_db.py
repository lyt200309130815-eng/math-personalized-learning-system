"""Create the V0.1 schema and insert function-topic seed data safely."""

import csv
import json
from contextlib import closing
from pathlib import Path

from database.database import DATABASE_PATH, get_connection


QUESTION_PATH = Path(__file__).resolve().parent / "data" / "questions.csv"

KNOWLEDGE_POINTS = [
    ("K001", "函数概念", "函数", None, [], "理解函数的对应关系和唯一性。"),
    ("K002", "定义域", "函数", None, ["K001"], "根据表达式限制确定自变量的取值范围。"),
    ("K003", "函数单调性", "函数", None, ["K001", "K002"], "在给定定义域内判断函数的增减性。"),
    ("K004", "函数最值", "函数", None, ["K002", "K003"], "结合定义域和单调性求函数的最大值与最小值。"),
    ("K005", "含参数函数", "函数", None, ["K003", "K004"], "利用单调性和最值分析函数中的参数范围。"),
]

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS knowledge_points (
        id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        topic TEXT NOT NULL,
        parent_id TEXT REFERENCES knowledge_points(id),
        prerequisite_ids TEXT NOT NULL DEFAULT '[]',
        description TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY NOT NULL,
        stem TEXT NOT NULL,
        options TEXT NOT NULL,
        answer TEXT NOT NULL CHECK (answer IN ('A', 'B', 'C', 'D')),
        explanation TEXT NOT NULL,
        knowledge_point_id TEXT NOT NULL REFERENCES knowledge_points(id),
        difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
        ability_tag TEXT NOT NULL,
        question_type TEXT NOT NULL DEFAULT 'single_choice'
            CHECK (question_type = 'single_choice'),
        estimated_time INTEGER NOT NULL CHECK (estimated_time > 0)
    )""",
    """CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL CHECK (length(trim(student_id)) > 0),
        question_id TEXT NOT NULL REFERENCES questions(id),
        user_answer TEXT NOT NULL CHECK (user_answer IN ('A', 'B', 'C', 'D')),
        is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
        answer_time REAL NOT NULL CHECK (answer_time >= 0),
        hint_count INTEGER NOT NULL DEFAULT 0 CHECK (hint_count >= 0),
        retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
        error_type TEXT CHECK (error_type IN ('K', 'C', 'L', 'M', 'R', 'S')),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )""",
)


def initialize_database(database_path: str | Path = DATABASE_PATH) -> None:
    """Create tables and add missing seeds without replacing existing records."""
    with QUESTION_PATH.open(encoding="utf-8-sig", newline="") as source:
        questions = list(csv.DictReader(source))

    with closing(get_connection(database_path)) as connection:
        with connection:
            for statement in SCHEMA:
                connection.execute(statement)
            connection.executemany(
                """INSERT INTO knowledge_points
                   (id, name, topic, parent_id, prerequisite_ids, description)
                   VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING""",
                [(key, name, topic, parent, json.dumps(prerequisites), description)
                 for key, name, topic, parent, prerequisites, description
                 in KNOWLEDGE_POINTS],
            )
            # JSON lists cannot have SQLite foreign keys; validate every reference.
            rows = connection.execute(
                "SELECT id, prerequisite_ids FROM knowledge_points"
            ).fetchall()
            known_ids = {row["id"] for row in rows}
            for row in rows:
                prerequisites = json.loads(row["prerequisite_ids"])
                if not isinstance(prerequisites, list) or any(
                    not isinstance(key, str) or key not in known_ids
                    or key == row["id"] for key in prerequisites
                ):
                    raise ValueError(f"Invalid prerequisites for {row['id']}")

            for question in questions:
                options = json.loads(question["options"])
                if not isinstance(options, dict) or set(options) != {"A", "B", "C", "D"}:
                    raise ValueError(f"Invalid options for {question['id']}")
                connection.execute(
                    """INSERT INTO questions
                       (id, stem, options, answer, explanation, knowledge_point_id,
                        difficulty, ability_tag, question_type, estimated_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO NOTHING""",
                    (question["id"], question["stem"],
                     json.dumps(options, ensure_ascii=False), question["answer"],
                     question["explanation"], question["knowledge_point_id"],
                     int(question["difficulty"]), question["ability_tag"],
                     question["question_type"], int(question["estimated_time"])),
                )


if __name__ == "__main__":
    initialize_database()
    with closing(get_connection()) as connection:
        point_count = connection.execute("SELECT COUNT(*) FROM knowledge_points").fetchone()[0]
        question_count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    print(f"数据库初始化完成：{DATABASE_PATH}")
    print(f"知识点：{point_count}；题目：{question_count}。已有记录保持不变。")
