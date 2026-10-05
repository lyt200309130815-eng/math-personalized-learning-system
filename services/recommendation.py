"""Explainable, read-only recommendations with recursive prerequisite checks."""

import json
from pathlib import Path

from database.database import (
    DATABASE_PATH, get_function_knowledge_points, get_questions_for_knowledge, get_recent_attempts,
)
from services.mastery import calculate_knowledge_mastery, calculate_student_mastery


def get_recommendation_type(mastery: dict) -> str:
    """Evidence changes strategy, never the mastery score itself."""
    score = mastery["mastery_score"]
    if score is None:
        return "诊断"
    if score < 0.60:
        return "补弱"
    if score < 0.80:
        return "巩固"
    return "提升" if mastery["evidence_level"] == "数据较充分" else "验证"


def get_difficulty_range(mastery: dict) -> tuple[int, int]:
    """Map actual mastery and strategy to a preferred difficulty band."""
    score = mastery["mastery_score"]
    if score is None or score < 0.40:
        return (1, 2)
    if score < 0.60 or get_recommendation_type(mastery) == "验证":
        return (2, 3)
    if score < 0.80:
        return (3, 4)
    return (4, 5)


def _priority(mastery: dict, depth: int = 0) -> tuple:
    score = mastery["mastery_score"]
    category = (0 if score is None else 1 if score < 0.40 else 2 if score < 0.60
                else 3 if score < 0.80 else 4 if get_recommendation_type(mastery) == "验证" else 5)
    if category == 4:
        evidence_rank = {"无数据": 0, "数据较少": 1, "初步判断": 2, "数据较充分": 3}
        return (category, evidence_rank[mastery["evidence_level"]],
                mastery["attempt_count"], mastery["knowledge_point_id"])
    if category == 5:
        return (category, -depth, score, mastery["attempt_count"], mastery["knowledge_point_id"])
    return (category, -1 if score is None else score, mastery["attempt_count"], mastery["knowledge_point_id"])


def recommend_next_knowledge(
    student_id: str, *, database_path: str | Path = DATABASE_PATH,
) -> dict:
    """Choose a priority target, then recursively fall back to unmet prerequisites."""
    results = calculate_student_mastery(student_id, database_path=database_path)
    if not results:
        raise ValueError("函数知识点尚未初始化。")
    mastery_by_id = {result["knowledge_point_id"]: result for result in results}
    prerequisites = {}
    for point in get_function_knowledge_points(database_path=database_path):
        keys = json.loads(point["prerequisite_ids"])
        if not isinstance(keys, list) or any(not isinstance(key, str) or key not in mastery_by_id for key in keys):
            raise ValueError(f"知识点 {point['id']} 的前置关系无效。")
        prerequisites[point["id"]] = keys

    depths = {}

    def knowledge_depth(key: str, path: tuple[str, ...] = ()) -> int:
        if key in path:
            raise ValueError("知识点前置关系存在循环。")
        if key not in depths:
            depths[key] = max((knowledge_depth(parent, path + (key,)) + 1
                               for parent in prerequisites[key]), default=0)
        return depths[key]

    for key in prerequisites:
        knowledge_depth(key)

    def resolve(key: str, path: tuple[str, ...] = ()) -> str:
        if key in path:
            raise ValueError("知识点前置关系存在循环。")
        resolved_parents = {resolve(parent, path + (key,)) for parent in prerequisites[key]}
        candidates = {parent for parent in resolved_parents
                      if mastery_by_id[parent]["mastery_score"] is None
                      or mastery_by_id[parent]["mastery_score"] < 0.60}
        if not candidates:
            return key
        return min(candidates, key=lambda candidate: _priority(mastery_by_id[candidate]))

    origin = min(results, key=lambda result: _priority(result, depths[result["knowledge_point_id"]]))
    target = mastery_by_id[resolve(origin["knowledge_point_id"])]
    strategy = get_recommendation_type(target)
    score = target["mastery_score"]
    name = target["knowledge_point_name"]
    if all(result["attempt_count"] == 0 for result in results):
        reason = "当前暂无训练数据，建议从函数基础知识开始进行诊断训练。"
    elif score is None:
        reason = f"{name}尚未评估，建议先进行基础诊断训练。"
    elif strategy == "补弱":
        reason = f"{name}当前掌握度为{score:.0%}，属于{target['mastery_level']}，建议优先补弱训练。"
    elif strategy == "巩固":
        reason = f"{name}当前掌握度为{score:.0%}，建议通过适当难度训练巩固基础。"
    elif strategy == "验证":
        reason = f"{name}当前掌握度为{score:.0%}，但证据量为{target['evidence_level']}，建议少量验证训练。"
    else:
        reason = f"{name}当前掌握度为{score:.0%}且数据较充分，建议进行更高难度的提升训练。"
    if target["knowledge_point_id"] != origin["knowledge_point_id"]:
        status = "尚未评估" if score is None else "尚未达到60%"
        reason = f"训练{origin['knowledge_point_name']}前，需要先验证或补强前置知识；{name}{status}。" + reason
    return {**target, "recommendation_type": strategy, "reason": reason,
            "difficulty_range": list(get_difficulty_range(target))}


def _select_questions(student_id: str, target: dict, limit: int, database_path: str | Path) -> list[dict]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    questions = get_questions_for_knowledge(target["knowledge_point_id"], database_path=database_path)
    recent_ids = {row["question_id"] for row in get_recent_attempts(student_id, 10, database_path=database_path)}
    low, high = get_difficulty_range(target)

    def sort_key(question: dict) -> tuple:
        difficulty = question["difficulty"]
        distance = max(low - difficulty, 0, difficulty - high)
        return (question["id"] in recent_ids, distance, difficulty, question["id"])

    return [{**question, "recently_practiced": question["id"] in recent_ids,
             "difficulty_fallback": not low <= question["difficulty"] <= high}
            for question in sorted(questions, key=sort_key)[:limit]]


def recommend_questions(
    student_id: str, knowledge_point_id: str, limit: int = 5, *, database_path: str | Path = DATABASE_PATH,
) -> list[dict]:
    """Select unique previews for a given point; new questions precede recent ones."""
    target = calculate_knowledge_mastery(student_id, knowledge_point_id, database_path=database_path)
    return _select_questions(student_id, target, limit, database_path)


def generate_recommendation(
    student_id: str, limit: int = 5, *, database_path: str | Path = DATABASE_PATH,
) -> dict:
    """Return a prerequisite-safe target and practice previews, without writing data."""
    target = recommend_next_knowledge(student_id, database_path=database_path)
    return {"student_id": student_id, "target_knowledge": target,
            "recommended_questions": _select_questions(student_id, target, limit, database_path)}
