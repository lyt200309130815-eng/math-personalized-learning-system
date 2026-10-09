"""Explainable, read-only recommendations with recursive prerequisite checks."""

import json
from pathlib import Path

from database.database import (
    DATABASE_PATH, get_function_knowledge_points, get_questions_for_knowledge, get_recent_attempts,
    get_question_prerequisites,
    get_recent_question_ids,
)
from settings import get_active_taxonomy_version
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
    if mastery.get('knowledge_point_id', '').startswith('G'):
        from services.geometry_quality import geometry_difficulty_range
        return geometry_difficulty_range(mastery)
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
    student_id: str, *, database_path: str | Path | None = None, taxonomy_version: str | None = None,
    knowledge_point_id: str | None = None,
) -> dict:
    """Choose a priority target, then recursively fall back to unmet prerequisites."""
    kwargs = {'database_path': database_path}
    if taxonomy_version is not None: kwargs['taxonomy_version'] = taxonomy_version
    results = calculate_student_mastery(student_id, **kwargs)
    if not results:
        raise ValueError("函数知识点尚未初始化。")
    mastery_by_id = {result["knowledge_point_id"]: result for result in results}
    prerequisites = {}
    for point in get_function_knowledge_points(**kwargs):
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

    if knowledge_point_id is not None and knowledge_point_id not in mastery_by_id:
        raise ValueError('未知知识点。')
    origin = (mastery_by_id[knowledge_point_id] if knowledge_point_id is not None else
              min(results, key=lambda result: _priority(result, depths[result["knowledge_point_id"]])))
    target = mastery_by_id[resolve(origin["knowledge_point_id"])]
    strategy = get_recommendation_type(target)
    score = target["mastery_score"]
    name = target["knowledge_point_name"]
    if all(result["attempt_count"] == 0 for result in results):
        from settings import get_topic_name
        reason = "当前暂无训练数据，建议从" + get_topic_name(taxonomy_version) + "基础知识开始进行诊断训练。"
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
    if target.get('evidence_status') == 'insufficient':
        reason = f'{name}：证据不足 / 待进一步训练；先验证独立原题与必要前置知识。'
    return {**target, "recommendation_type": strategy, "reason": reason,
            "difficulty_range": list(get_difficulty_range(target))}


def _select_questions(student_id: str, target: dict, limit: int, database_path, taxonomy_version=None) -> list[dict]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    kwargs = {'database_path': database_path}
    if taxonomy_version is not None: kwargs['taxonomy_version'] = taxonomy_version
    questions = get_questions_for_knowledge(target["knowledge_point_id"], **kwargs)
    if (taxonomy_version or get_active_taxonomy_version()) != 'function_v1':
        mastery = {p['knowledge_point_id']:p for p in calculate_student_mastery(student_id, **kwargs)}
        points = get_function_knowledge_points(**kwargs)
        graph = {p['id']:json.loads(p['prerequisite_ids']) for p in points}
        def ready(key, trail=()):
            if key in trail: raise ValueError('前置关系存在循环。')
            score = mastery[key]['mastery_score']
            return score is not None and score>=0.60 and all(ready(p,trail+(key,)) for p in graph[key])
        if any(not ready(p) for p in graph[target['knowledge_point_id']]): return []
        questions = [q for q in questions if all(ready(p) for p in get_question_prerequisites(q['id'], taxonomy_version or get_active_taxonomy_version(), database_path=database_path))]
    recent_ids = (set(get_recent_question_ids(student_id,database_path=database_path))
                  if (taxonomy_version or get_active_taxonomy_version()) != 'function_v1'
                  else {row['question_id'] for row in get_recent_attempts(student_id,10,**kwargs)})
    geometry = (taxonomy_version or get_active_taxonomy_version()) == 'geometry_v1'
    if geometry:
        from database.database import get_approved_questions
        from services.geometry_quality import geometry_identity_tokens
        full_pool = get_approved_questions(**kwargs)
        identities = {q['id']: geometry_identity_tokens(q) for q in full_pool}
        recent_sources = set().union(*(identities[key] for key in recent_ids if key in identities)) if recent_ids else set()
        for q in questions:
            if identities.get(q['id'], set()) & recent_sources:
                recent_ids.add(q['id'])
    low, high = get_difficulty_range(target)

    def sort_key(question: dict) -> tuple:
        difficulty = question["difficulty"]
        distance = max(low - difficulty, 0, difficulty - high)
        return (question["id"] in recent_ids, distance, difficulty, question["id"])

    ordered = sorted(questions, key=sort_key)
    if geometry:
        from services.question_type_policy import select_question_type
        selected = []
        while ordered and len(selected) < limit:
            fresh = [q for q in ordered if q['id'] not in recent_ids]
            pool = fresh or ordered
            near = [q for q in pool if low <= q['difficulty'] <= high]
            pool = near or pool
            kind, _ = select_question_type(pool, selected, target['mastery_score'])
            q = min([q for q in pool if q['question_type'] == kind], key=sort_key)
            selected.append(q)
            ordered.remove(q)
        ordered = selected
    return [{**question, "recently_practiced": question["id"] in recent_ids,
             "difficulty_fallback": not low <= question["difficulty"] <= high}
            for question in ordered[:limit]]


def recommend_questions(
    student_id: str, knowledge_point_id: str, limit: int = 5, *, database_path: str | Path | None = None, taxonomy_version: str | None = None,
) -> list[dict]:
    """Select unique previews for a given point; new questions precede recent ones."""
    kwargs={'database_path':database_path}
    if taxonomy_version is not None: kwargs['taxonomy_version']=taxonomy_version
    target = calculate_knowledge_mastery(student_id, knowledge_point_id, **kwargs)
    return _select_questions(student_id, target, limit, database_path, taxonomy_version)


def generate_recommendation(
    student_id: str, limit: int = 5, *, database_path: str | Path | None = None, taxonomy_version: str | None = None,
) -> dict:
    """Return a prerequisite-safe target and practice previews, without writing data."""
    kwargs={'database_path':database_path}
    if taxonomy_version is not None: kwargs['taxonomy_version']=taxonomy_version
    target = recommend_next_knowledge(student_id, **kwargs)
    questions = _select_questions(student_id, target, limit, database_path, taxonomy_version)
    result = {"student_id": student_id, "target_knowledge": target, "recommended_questions": questions}
    if (taxonomy_version or get_active_taxonomy_version()) == 'geometry_v1':
        from database.database import get_approved_questions
        available = get_approved_questions(target['knowledge_point_id'], **kwargs)
        levels = sorted({q['difficulty'] for q in available})
        low, high = get_difficulty_range(target)
        missing = [d for d in range(low, high+1) if d not in levels]
        result['coverage_limitations'] = ([f"题库覆盖不足（coverage limitation）：{target['knowledge_point_name']}缺少" + '/'.join(f'D{d}' for d in missing) + '，待审恢复题不参与推荐。'] if missing else [])
        result['available_difficulties'] = levels
        result['status'] = 'ready' if questions else 'insufficient_eligible_questions'
        result['message'] = '可以开始训练。' if questions else '暂缺满足前置条件的正式练习；请先完成基础训练。'
    if (taxonomy_version or get_active_taxonomy_version())=='function_v2':
        if not questions and limit>0:
            for alternative in sorted(calculate_student_mastery(student_id, **kwargs),key=_priority):
                eligible=_select_questions(student_id,alternative,limit,database_path,taxonomy_version)
                if eligible:
                    result['target_knowledge']={**alternative,'recommendation_type':get_recommendation_type(alternative),
                        'difficulty_range':list(get_difficulty_range(alternative)),
                        'reason':f"{target['knowledge_point_name']}当前缺少满足前置条件的已审核练习；先进行{alternative['knowledge_point_name']}的{get_recommendation_type(alternative)}训练。"}
                    result['recommended_questions']=eligible
                    break
        result['status']='ready' if result['recommended_questions'] else 'insufficient_eligible_questions'
        result['message']='可以开始训练。' if result['recommended_questions'] else '暂缺满足前置条件的已审核练习，请先完成必要基础训练。'
    return result
