"""Convert existing mastery results into display data without recalculating scores."""

from collections.abc import Sequence


def format_percentage(value: float | None) -> str:
    """Keep missing evidence distinct from a measured zero."""
    return "未评估" if value is None else f"{value:.0%}"


def build_profile_data(mastery_results: Sequence[dict]) -> dict:
    """Format metrics, aggregate counts, and omit unevaluated points from charts."""
    points = []
    chart = []
    unevaluated = []
    metric_fields = ("overall_accuracy", "recent_accuracy", "stability",
                     "difficulty_performance", "mastery_score")
    for result in mastery_results:
        point = dict(result)
        point["mastery_display"] = format_percentage(result["mastery_score"])
        point["metric_displays"] = {field: format_percentage(result[field]) for field in metric_fields}
        point["evidence_note"] = (
            "当前表现较好，但训练数据较少，建议继续训练以提高判断可靠性。"
            if result["mastery_score"] is not None and result["mastery_score"] >= 0.80
            and result["evidence_level"] == "数据较少" else None
        )
        points.append(point)
        if result["mastery_score"] is None:
            unevaluated.append(f"{result['knowledge_point_id']} {result['knowledge_point_name']}")
        else:
            chart.append({"知识点": f"{result['knowledge_point_id']} {result['knowledge_point_name']}",
                          "掌握度（%）": result["mastery_score"] * 100})
    total_attempts = sum(point["attempt_count"] for point in points)
    total_correct = sum(point["correct_count"] for point in points)
    return {
        "points": points, "chart": chart, "unevaluated": unevaluated,
        "chart_spec": {
            "data": {"values": chart},
            "mark": "bar",
            "encoding": {
                "x": {"field": "掌握度（%）", "type": "quantitative",
                      "scale": {"domain": [0, 100]},
                      "axis": {"title": "掌握度（%）", "values": [0, 20, 40, 60, 80, 100]}},
                "y": {"field": "知识点", "type": "nominal", "sort": None},
                "tooltip": [{"field": "知识点", "type": "nominal"},
                            {"field": "掌握度（%）", "type": "quantitative", "format": ".1f"}],
            },
        },
        "overview": {
            "knowledge_point_count": len(points),
            "trained_count": sum(point["attempt_count"] > 0 for point in points),
            "unevaluated_count": len(unevaluated), "total_attempts": total_attempts,
            "overall_accuracy_display": (
                format_percentage(total_correct / total_attempts) if total_attempts else "暂无数据"),
        },
    }
