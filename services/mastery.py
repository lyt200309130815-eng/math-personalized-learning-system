"""Deterministic knowledge mastery calculated only from structured evidence."""

from pathlib import Path
from statistics import pstdev
from settings import get_active_taxonomy_version

from database.database import (
    DATABASE_PATH, get_function_knowledge_points, get_knowledge_attempts, get_knowledge_point,
)


def get_mastery_level(score: float | None) -> str:
    """Classify an unrounded score; each threshold belongs to the higher level."""
    if score is None:
        return "未评估"
    if not 0 <= score <= 1:
        raise ValueError("mastery score must be between 0 and 1")
    for threshold, level in ((0.40, "明显薄弱"), (0.60, "基础不足"),
                             (0.80, "基本掌握"), (0.90, "熟练")):
        if score < threshold:
            return level
    return "稳定掌握"


def get_evidence_level(attempt_count: int) -> str:
    """Describe evidence volume without influencing the numeric score."""
    if attempt_count < 0:
        raise ValueError("attempt_count must be nonnegative")
    if attempt_count == 0:
        return "无数据"
    if attempt_count <= 2:
        return "数据较少"
    if attempt_count <= 5:
        return "初步判断"
    return "数据较充分"


def calculate_knowledge_mastery(
    student_id: str, knowledge_point_id: str, *, database_path: str | Path | None = None, taxonomy_version: str | None = None,
    connection=None,
) -> dict:
    """Return all evidence and metrics for one point; never persist derived scores.

    R and S use the newest five records by created_at (ID breaks ties).
    Unknown knowledge IDs raise ValueError rather than masquerading as untrained points.
    """
    kwargs = {'database_path': database_path}
    if taxonomy_version is not None: kwargs['taxonomy_version'] = taxonomy_version
    point = get_knowledge_point(knowledge_point_id, **kwargs)
    if point is None:
        raise ValueError(f"Unknown knowledge point: {knowledge_point_id}")
    attempt_kwargs = {**kwargs, 'connection': connection} if connection is not None else kwargs
    attempts = get_knowledge_attempts(student_id, knowledge_point_id, **attempt_kwargs)
    count = len(attempts)
    correct_count = sum(row["is_correct"] for row in attempts)
    result = {
        "knowledge_point_id": point["id"], "knowledge_point_name": point["name"],
        "attempt_count": count, "correct_count": correct_count,
        "overall_accuracy": None, "recent_accuracy": None, "stability": None,
        "difficulty_performance": None, "mastery_score": None,
        "mastery_level": "未评估", "evidence_level": get_evidence_level(count),
    }
    if (taxonomy_version or get_active_taxonomy_version()) == 'geometry_v1':
        from database.database import get_approved_questions
        from services.geometry_quality import source_fingerprint
        pool = get_approved_questions(knowledge_point_id, database_path=database_path, taxonomy_version='geometry_v1')
        identities = {q['id']: source_fingerprint(q) for q in pool}
        evidence_count = len({identities.get(a['question_id']) or a['question_id'] for a in attempts})
        result.update(source_evidence_count=evidence_count, coverage_available=len(pool),
                      evidence_status='insufficient' if evidence_count < 3 else 'sufficient',
                      mastery_display='证据不足 / 待进一步训练' if evidence_count < 3 else None)
    if not attempts:
        return result
    overall_accuracy = correct_count / count
    recent_results = [row["is_correct"] for row in attempts[:5]]
    recent_accuracy = sum(recent_results) / len(recent_results)
    stability = min(1.0, max(0.0, recent_accuracy * (1 - pstdev(recent_results))))
    difficulty_performance = (
        sum(row["is_correct"] * row["difficulty"] for row in attempts)
        / sum(row["difficulty"] for row in attempts)
    )
    score = min(1.0, max(0.0, 0.50 * overall_accuracy + 0.20 * recent_accuracy
                         + 0.15 * stability + 0.15 * difficulty_performance))
    result.update(overall_accuracy=overall_accuracy, recent_accuracy=recent_accuracy,
                  stability=stability, difficulty_performance=difficulty_performance,
                  mastery_score=score, mastery_level=get_mastery_level(score))
    if result.get('evidence_status') == 'sufficient':
        result['mastery_display'] = f'{score:.0%}'
    return result


def calculate_student_mastery(
    student_id: str, *, database_path: str | Path | None = None, taxonomy_version: str | None = None,
) -> list[dict]:
    """Return all configured taxonomy points, retaining those without evidence."""
    kwargs = {'database_path': database_path}
    if taxonomy_version is not None: kwargs['taxonomy_version'] = taxonomy_version
    return [calculate_knowledge_mastery(student_id, point["id"], **kwargs)
            for point in get_function_knowledge_points(**kwargs)]
