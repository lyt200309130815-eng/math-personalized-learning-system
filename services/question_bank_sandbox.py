"""Temporary v2 integration adapters; never activated by the production app."""

from contextlib import closing, contextmanager, ExitStack
import json
import os
from pathlib import Path
from unittest.mock import patch

from database.database import DATABASE_PATH, get_connection, record_attempt
from init_db import SCHEMA
from services.mastery import calculate_knowledge_mastery
from services.question_importer import get_approved_questions, import_questions
from services.question_validator import load_taxonomy


def require_isolated_path(path: Path) -> Path:
    path = Path(path).resolve()
    if path == DATABASE_PATH.resolve() or (path.exists() and DATABASE_PATH.exists() and os.path.samefile(path, DATABASE_PATH)):
        raise ValueError("禁止使用真实 math_ai.db。")
    return path


def create_sandbox(path: Path, approved: list[dict]) -> None:
    """Build only in a new temporary file; no legacy student data is copied."""
    path = require_isolated_path(path)
    if path.exists():
        raise ValueError("沙盒必须使用新建的隔离数据库。")
    with closing(get_connection(path)) as connection:
        with connection:
            for statement in SCHEMA:
                connection.execute(statement)
    result = import_questions(approved, database_path=path)
    if result["errors"] or result["rejected"]:
        raise ValueError("沙盒只允许校验通过的 approved 题。")
    points = load_taxonomy()["knowledge_points"]
    with closing(get_connection(path)) as connection:
        with connection:
            connection.executemany("INSERT INTO knowledge_points VALUES (?, ?, ?, ?, ?, ?)",
                [(p["id"], p["name"], "函数", None, json.dumps(p["prerequisite_ids"]), "临时 function_v2 验收") for p in points])
            rows = [row for p in points for row in get_approved_questions(p["id"], database_path=path)] if approved else []
            connection.executemany("INSERT INTO questions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(row["id"], row["stem"], json.dumps(row["options"], ensure_ascii=False), row["answer"], row["explanation"],
                  row["primary_knowledge_point_id"], row["difficulty"], row["ability_tags"][0], "single_choice", row["estimated_time"]) for row in rows])


def _bank_exists(connection) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", ("approved_question_bank",)).fetchone() is not None


def training_questions(path: Path) -> list[dict]:
    """Whitelisted student fields only; explicit approval gate in the SQL."""
    path = require_isolated_path(path)
    with closing(get_connection(path, read_only=True)) as connection:
        if not _bank_exists(connection): return []
        rows = connection.execute("""SELECT q.id, q.stem, q.options, q.answer, q.explanation,
            b.primary_knowledge_point_id AS knowledge_point_id, k.name AS knowledge_point_name,
            q.difficulty, q.estimated_time FROM questions q JOIN approved_question_bank b ON b.id=q.id
            JOIN bank_knowledge_points k ON k.id=b.primary_knowledge_point_id AND k.taxonomy_version=b.taxonomy_version
            WHERE b.quality_status = ? AND b.taxonomy_version = ? ORDER BY q.id""", ("approved", "function_v2")).fetchall()
    return [{**dict(row), "options": json.loads(row["options"])} for row in rows]


@contextmanager
def bank_service_context(path: Path, student_id: str = "S001"):
    """Scope query redirection to disposable DBs; calculations retain original rules.

    This context is for CLI/AppTest acceptance only, not concurrent serving.
    All default database arguments are redirected to the sandbox, never production.
    """
    path = require_isolated_path(path)

    def points(*, database_path=None):
        with closing(get_connection(path, read_only=True)) as connection:
            return connection.execute("SELECT * FROM knowledge_points WHERE topic=? ORDER BY id", ("函数",)).fetchall()

    def point(key, *, database_path=None):
        with closing(get_connection(path, read_only=True)) as connection:
            return connection.execute("SELECT * FROM knowledge_points WHERE id=?", (key,)).fetchone()

    def attempts(student, key, *, database_path=None):
        with closing(get_connection(path, read_only=True)) as connection:
            if not _bank_exists(connection): return []
            return connection.execute("""SELECT a.id,a.is_correct,q.difficulty,a.created_at,a.question_id
                FROM attempts a JOIN questions q ON q.id=a.question_id JOIN approved_question_bank b ON b.id=q.id
                WHERE a.student_id=? AND b.primary_knowledge_point_id=? AND b.taxonomy_version=? AND b.quality_status=?
                ORDER BY a.created_at DESC,a.id DESC""", (student, key, "function_v2", "approved")).fetchall()

    def recent(student, limit=10, *, database_path=None):
        with closing(get_connection(path, read_only=True)) as connection:
            if not _bank_exists(connection): return []
            return connection.execute("""SELECT a.* FROM attempts a JOIN approved_question_bank b ON b.id=a.question_id
                WHERE a.student_id=? AND b.quality_status=? AND b.taxonomy_version=?
                ORDER BY a.created_at DESC,a.id DESC LIMIT ?""", (student, "approved", "function_v2", limit)).fetchall()

    def previews(key, *, database_path=None):
        bank = get_approved_questions(key, database_path=path) if Path(path).exists() else []
        def ready(parent, trail=()):
            if parent in trail:
                raise ValueError("前置知识关系存在循环。")
            metadata = point(parent)
            if metadata is None:
                return False
            score = calculate_knowledge_mastery(student_id, parent, database_path=path)["mastery_score"]
            return score is not None and score >= 0.60 and all(
                ready(ancestor, trail + (parent,)) for ancestor in json.loads(metadata["prerequisite_ids"]))
        if any(not ready(parent) for parent in json.loads(point(key)["prerequisite_ids"])):
            return []
        eligible = []
        for row in bank:
            required = row["question_prerequisite_ids"]
            if any(not ready(parent) for parent in required):
                continue
            eligible.append({"id": row["id"], "stem": row["stem"], "difficulty": row["difficulty"],
                             "knowledge_point_id": key, "knowledge_point_name": point(key)["name"]})
        return eligible

    def recorder(**kwargs):
        if kwargs["question_id"] not in {row["id"] for row in training_questions(path)}:
            raise ValueError("非 approved 题不能提交。")
        return record_attempt(**kwargs, database_path=path)

    with ExitStack() as stack:
        for module in ("mastery", "recommendation"):
            stack.enter_context(patch(f"services.{module}.get_function_knowledge_points", side_effect=points))
        stack.enter_context(patch("services.mastery.get_knowledge_point", side_effect=point))
        stack.enter_context(patch("services.mastery.get_knowledge_attempts", side_effect=attempts))
        stack.enter_context(patch("services.recommendation.get_recent_attempts", side_effect=recent))
        stack.enter_context(patch("services.recommendation.get_questions_for_knowledge", side_effect=previews))
        stack.enter_context(patch("database.database.get_training_questions", side_effect=lambda *a, **k: training_questions(path)))
        stack.enter_context(patch("services.training.record_attempt", side_effect=recorder))
        yield


def sandbox_recommendation(student_id: str, path: Path, limit: int = 5) -> dict:
    from services.recommendation import generate_recommendation
    with bank_service_context(path, student_id):
        result = generate_recommendation(student_id, limit, database_path=path)
    target = result["target_knowledge"]["knowledge_point_id"]
    if result["recommended_questions"]:
        result.update(status="ready", message="可以开始训练。")
    elif not get_approved_questions(target, database_path=path):
        result.update(status="insufficient_coverage", message=f"{target} 暂无金标准题，题库覆盖不足。")
    else:
        result.update(status="question_prerequisites_unmet", message="当前题目的前置知识尚未验证，请先完成基础训练。")
    return result
