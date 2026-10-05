"""Deterministic coverage diagnostics; never affect mastery scores."""

from collections import Counter
from pathlib import Path

from services.question_review import atomic_write
from services.question_validator import load_taxonomy


def build_coverage_report(questions: list[dict]) -> dict:
    points = []
    for point in load_taxonomy()["knowledge_points"]:
        rows = [row for row in questions if row.get("quality_status") == "approved"
                and row.get("taxonomy_version") == "function_v2"
                and row.get("primary_knowledge_point_id") == point["id"]]
        difficulty = Counter(row["difficulty"] for row in rows)
        foundation = sum(difficulty[d] for d in (1, 2))
        consolidation = sum(difficulty[d] for d in (2, 3))
        gaps = []
        if not rows: gaps.append("P0")
        if len(rows) < 3: gaps.append("P1")
        if not foundation: gaps.append("P2")
        if not consolidation: gaps.append("P3")
        priority = gaps[0] if gaps else "P4"
        points.append({"knowledge_point_id": point["id"], "knowledge_point_name": point["name"],
                       "approved_count": len(rows), "difficulty_distribution": {str(i): difficulty[i] for i in range(1, 6)},
                       "foundation_count": foundation, "consolidation_count": consolidation,
                       "status": "insufficient_coverage" if gaps else "sufficient_coverage",
                       "priority": priority, "gaps": gaps,
                       "advanced_count": sum(difficulty[d] for d in (4, 5))})
    return {"points": points, "status": "insufficient_coverage" if any(p["gaps"] for p in points) else "sufficient_coverage",
            "suggested_order": [p["knowledge_point_id"] for p in sorted(points, key=lambda p: (p["priority"], p["knowledge_point_id"]))]}


def write_gap_report(questions: list[dict], path: Path) -> dict:
    coverage = build_coverage_report(questions)
    lines = ["# Batch 001 金标准题覆盖与 Batch 002 缺口分析", "",
             "仅分析缺口，没有提取或生成 Batch 002，不修改 mastery、数据库或学生数据。",
             "建议门槛：每节点至少3道 approved，至少1道难度1–2、至少1道难度2–3；同一道难度2题可满足两类难度条件。",
             "P0 无题；P1 少于3题；P2 缺基础诊断题；P3 缺巩固题；P4 后续才考虑难度4–5。并列按知识点ID排序。",
             "coverage 状态只评价题库覆盖，不代表学生能力。", "",
             f"整体状态：{coverage['status']}", "", "| 知识点 | approved | d1 | d2 | d3 | d4 | d5 | 状态 | 优先级/缺口 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for point in coverage["points"]:
        counts = " | ".join(str(point["difficulty_distribution"][str(i)]) for i in range(1, 6))
        lines.append(f"| {point['knowledge_point_id']} {point['knowledge_point_name']} | {point['approved_count']} | {counts} | {point['status']} | {point['priority']} / {','.join(point['gaps']) or '基础门槛已满足'} |")
    lines += ["", "## 建议补题顺序", "", " → ".join(coverage["suggested_order"]), "",
              "先补 K007 二次函数（P0），再按 P1/P2/P3 缺口补足已有节点。P4 表示后续扩展，不优先于基础覆盖。",
              "K007 当前 approved=0；Batch 001 可作为首批金标准题，function_v2 题库覆盖尚不完整。", ""]
    atomic_write(path, "\n".join(lines))
    return coverage
