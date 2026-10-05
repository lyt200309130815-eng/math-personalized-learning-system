"""Offline candidate contract and conservative completeness checks."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data/source_mapping.json"
EXTRACTION_STATUSES = {"complete", "formula_warning", "image_required", "incomplete", "manual_review"}
QUALITY_STATUSES = {"draft", "reviewed", "approved", "rejected"}


def load_taxonomy() -> dict:
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def content_fingerprint(candidate: dict) -> str:
    """Deduplicate content across sources; preserve answer/options differences."""
    def normalize(value):
        if isinstance(value, str):
            return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items())}
        return value
    fields = {key: normalize(candidate.get(key)) for key in ("stem", "options", "answer")}
    if isinstance(fields["stem"], str):
        fields["stem"] = re.sub(r"^(?:(?:例|跟踪训练)\s*\d+\s*)?(?:\([12]\)|（[12]）)\s*|^(?:例|跟踪训练)\s*\d+\s*|^\d+[.．、](?!\d)\s*", "", fields["stem"])
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def validate_candidate(candidate: dict) -> dict:
    """Return errors/warnings; approved requires explicit review and zero warnings."""
    errors, warnings = [], []
    taxonomy = load_taxonomy()
    known = {point["id"] for point in taxonomy["knowledge_points"]}
    for field in ("id", "stem", "explanation", "source_type", "source_file", "source_section", "source_locator"):
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            errors.append(f"{field} 缺失")
    if "source_question_number" not in candidate:
        errors.append("source_question_number 字段缺失（未知可为 null）")
    options = candidate.get("options")
    if (not isinstance(options, dict) or set(options) != set("ABCD")
            or any(not isinstance(value, str) or not value.strip() for value in options.values())):
        errors.append("A/B/C/D 选项缺失或为空")
    if candidate.get("answer") not in tuple("ABCD"):
        errors.append("答案必须为单个 A/B/C/D")
    if candidate.get("taxonomy_version") != "function_v2":
        errors.append("知识体系必须为 function_v2")
    primary = candidate.get("primary_knowledge_point_id")
    if not isinstance(primary, str) or primary not in known:
        errors.append("主要知识点无效")
    for field in ("related_knowledge_point_ids", "question_prerequisite_ids"):
        values = candidate.get(field)
        if (not isinstance(values, list) or any(not isinstance(key, str) or key not in known for key in values)
                or (all(isinstance(key, str) for key in values) and len(values) != len(set(values)))):
            errors.append(f"{field} 无效")
        elif primary in values:
            errors.append(f"{field} 不能包含主要知识点自身")
    for field, vocabulary in (("ability_tags", taxonomy["ability_tags"]), ("method_tags", taxonomy["method_tags"])):
        values = candidate.get(field)
        if not isinstance(values, list) or not values or any(tag not in vocabulary for tag in values):
            errors.append(f"{field} 不在词表内或为空")
    if type(candidate.get("difficulty")) is not int or not 1 <= candidate["difficulty"] <= 5:
        errors.append("difficulty 必须为1–5整数")
    if type(candidate.get("estimated_time")) is not int or candidate["estimated_time"] <= 0:
        errors.append("estimated_time 必须为正整数")
    if type(candidate.get("version")) is not int or candidate["version"] < 1:
        errors.append("version 必须为正整数")
    if candidate.get("extraction_status") not in EXTRACTION_STATUSES:
        errors.append("extraction_status 无效")
    if candidate.get("quality_status") not in QUALITY_STATUSES:
        errors.append("quality_status 无效")
    if not isinstance(candidate.get("review_notes"), list):
        errors.append("review_notes 必须为列表")
    if candidate.get("fingerprint") != content_fingerprint(candidate):
        errors.append("fingerprint 与内容不一致")
    stem, explanation = candidate.get("stem", ""), candidate.get("explanation", "")
    for name, text in (("stem", stem), ("explanation", explanation)):
        if isinstance(text, str):
            if len(text.strip()) < (8 if name == "stem" else 6):
                warnings.append(f"{name} 太短")
            if re.search(r"[=＝+\-*/^]\s*$|[=＝]\s*[，。,；;]|\[公式待核\]|\[图片待核\]", text):
                warnings.append(f"{name} 数学表达式可能残缺")
            if "\ufffd" in text:
                warnings.append(f"{name} 含无法恢复的字符")
            if re.search(r"\b(?:lg|ln)\s*\([^\n，,]+?\)/\(", text):
                warnings.append(f"{name} 对数与分式的作用范围不明确，需核对原公式")
            if re.search(r"\^\(\)|_\(\)|\^\(\(\)\^|\^\([^)]*\)\^\(", text):
                warnings.append(f"{name} 上下标嵌套或主体缺失，需核对公式")
            if name == "explanation" and re.search(r"[，,；;：:]\s*$", text):
                warnings.append("解析以未结束的分句结尾")
    if isinstance(options, dict):
        for key, text in options.items():
            if isinstance(text, str) and re.search(r"[=＝+\-*/^]\s*$|\[公式待核\]|\[图片待核\]|\[选项边界待核\]", text):
                warnings.append(f"选项{key}公式可能缺失")
            if isinstance(text, str) and re.search(r"\^\(\)|_\(\)|sqrt\(\)", text):
                warnings.append(f"选项{key}公式主体缺失")
    body = "\n".join(text for text in (stem, explanation) if isinstance(text, str))
    if re.search(r"\b(?:sin|cos|tan)\b|三角函数", body):
        warnings.append("涉及未标注的三角函数基础，需人工确认可做性")
    if re.search(r"如图|下图|图中|图示|图所示|图象如", body):
        warnings.append("图象依赖尚未人工确认，需图片审核")
    if candidate.get("image_resources") or "[图片待核]" in body:
        warnings.append("包含未确认的图片资源")
    if candidate.get("extraction_status") != "complete":
        warnings.append("提取状态非 complete")
    if candidate.get("extraction_warnings"):
        warnings.extend(candidate["extraction_warnings"])
    conclusion = re.findall(r"(?:故选|选项|答案为|应选|选择)\s*([ABCD])(?:\s*[。．，,；;]|\s*$)", explanation if isinstance(explanation, str) else "")
    if conclusion and conclusion[-1] != candidate.get("answer"):
        warnings.append("解析结论与答案不一致")
    if candidate.get("quality_status") == "approved":
        confirmation = candidate.get("review_confirmation")
        if (not isinstance(confirmation, dict) or confirmation.get("confirmed") is not True
                or not isinstance(confirmation.get("reviewer"), str) or not confirmation["reviewer"].strip()
                or candidate.get("annotation_status") != "confirmed"):
            errors.append("approved 缺少明确人工确认")
    warnings = list(dict.fromkeys(warnings))
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "can_approve": not errors and not warnings and candidate.get("extraction_status") == "complete"}
