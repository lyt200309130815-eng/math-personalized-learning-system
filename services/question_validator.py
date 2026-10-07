"""Offline candidate contract and conservative completeness checks."""

import hashlib
import json
import re
import unicodedata
import math
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
    kind = candidate.get('question_type','single_choice')
    if kind != 'single_choice':
        fields.update({key:normalize(candidate.get(key)) for key in
                       ('question_type','answer_expression','accepted_answers','answer_type',
                        'reference_answer','solution_steps','rubric','max_score')})
    if kind == 'multiple_choice':
        answers = candidate.get('correct_answers')
        fields['correct_answers'] = sorted(answers) if isinstance(answers,list) and all(isinstance(a,str) for a in answers) else answers
    for key in ('canonical_answer', 'sub_questions', 'rubric_source', 'reference_answers_by_subquestion'):
        if key in candidate:
            fields[key] = normalize(candidate[key])
    if isinstance(fields["stem"], str):
        fields["stem"] = re.sub(r"^(?:(?:例|跟踪训练)\s*\d+\s*)?(?:\([12]\)|（[12]）)\s*|^(?:例|跟踪训练)\s*\d+\s*|^\d+[.．、](?!\d)\s*", "", fields["stem"])
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def validate_question_type(candidate: dict) -> list[str]:
    """Type-specific contract shared by import and training activation."""
    errors = []
    kind = candidate.get('question_type','single_choice')
    if kind not in ('single_choice','multiple_choice','fill_blank','subjective'):
        return ['question_type 必须为 single_choice/multiple_choice/fill_blank/subjective']
    if kind in ('single_choice', 'multiple_choice'):
        options = candidate.get('options')
        if (not isinstance(options,dict) or set(options)!=set('ABCD')
                or any(not isinstance(v,str) or not v.strip() for v in options.values())):
            errors.append('A/B/C/D 选项缺失或为空')
        elif len({unicodedata.normalize('NFKC',v).strip() for v in options.values()})!=4:
            errors.append('单选题选项必须互不相同，保证唯一答案')
        if kind == 'single_choice' and candidate.get('answer') not in tuple('ABCD'):
            errors.append('答案必须为单个 A/B/C/D')
        if kind == 'multiple_choice':
            answers = candidate.get('correct_answers')
            if (not isinstance(answers, list) or len(answers) < 2
                    or any(v not in tuple('ABCD') for v in answers)
                    or len(set(answers)) != len(answers)):
                errors.append('correct_answers 必须为至少两个不同有效选项的列表')
            if candidate.get('answer') is not None:
                errors.append('多选题不得使用单值 answer')
    elif kind == 'fill_blank':
        if candidate.get('options') is not None:
            errors.append('填空题不得提供 options')
        expression = candidate.get('canonical_answer') or candidate.get('answer_expression')
        accepted = candidate.get('accepted_answers')
        if expression is not None and (not isinstance(expression,str) or not expression.strip()):
            errors.append('answer_expression 必须为非空文本')
        if accepted is not None and (not isinstance(accepted,list) or not accepted
                or any(not isinstance(v,str) or not v.strip() for v in accepted)):
            errors.append('accepted_answers 必须为非空答案列表')
        if not expression and not accepted:
            errors.append('填空题必须有 accepted_answers 或 answer_expression')
        from services.answer_evaluator import ANSWER_TYPES, evaluate_fill_blank
        answer_type = candidate.get('answer_type')
        if answer_type not in ANSWER_TYPES:
            errors.append('填空题 answer_type 无效')
        elif not errors:
            try:
                for expected in ([expression] if expression else [])+(accepted or []):
                    if not evaluate_fill_blank(expected,expected,answer_type):
                        errors.append('标准答案无法确定性判分')
            except ValueError:
                errors.append('填空标准答案格式不受当前 evaluator 支持')
    else:
        if candidate.get('options') is not None:
            errors.append('主观题不得提供 options')
        if not isinstance(candidate.get('reference_answer'),str) or not candidate['reference_answer'].strip():
            errors.append('主观题必须有 reference_answer')
        rubric = candidate.get('rubric')
        score = candidate.get('max_score')
        if type(score) not in (int,float) or not math.isfinite(score) or score<=0:
            errors.append('max_score 必须为有限正数')
        if not isinstance(rubric,list) or not rubric or any(
            not isinstance(row,dict) or not isinstance(row.get('criterion'),str) or not row['criterion'].strip()
            or type(row.get('score')) not in (int,float) or not math.isfinite(row['score']) or row['score']<=0 for row in rubric):
            errors.append('rubric 必须为包含 criterion 和正数 score 的列表')
        elif type(score) in (int,float) and not math.isclose(sum(row['score'] for row in rubric),score):
            errors.append('rubric 分值合计必须等于 max_score')
        steps = candidate.get('solution_steps')
        if not isinstance(steps,list) or not steps or any(not isinstance(v,str) or not v.strip() for v in steps):
            errors.append('solution_steps 必须为非空文本列表')
        subs = candidate.get('sub_questions')
        if subs is not None:
            if (not isinstance(subs, list) or not subs or any(
                    not isinstance(s, dict) or not isinstance(s.get('id'), str)
                    or not s['id'] or not isinstance(s.get('stem'), str) or not s['stem'].strip()
                    or type(s.get('max_score')) not in (int, float)
                    or not math.isfinite(s['max_score']) or s['max_score'] <= 0 for s in subs)):
                errors.append('sub_questions 结构无效')
            else:
                ids = [s['id'] for s in subs]
                reference = candidate.get('reference_answers_by_subquestion')
                if (not isinstance(reference,dict) or set(reference)!=set(ids)
                        or any(not isinstance(v,str) or not v.strip() for v in reference.values())):
                    errors.append('reference_answers_by_subquestion 必须逐小问对应')
                if len(set(ids)) != len(ids): errors.append('小问 id 不得重复')
                if type(score) in (int, float) and not math.isclose(sum(s['max_score'] for s in subs), score):
                    errors.append('小问总分必须等于 max_score')
                if isinstance(rubric, list) and all(isinstance(r, dict) for r in rubric):
                    if any(r.get('sub_question') not in ids for r in rubric):
                        errors.append('rubric 必须引用有效小问')
                    else:
                        for s in subs:
                            values = [r.get('score') for r in rubric if r['sub_question'] == s['id']]
                            if all(type(v) in (int, float) for v in values) and not math.isclose(sum(values), s['max_score']):
                                errors.append('小问 rubric 分值不匹配')
            if candidate.get('rubric_source') not in ('derived_for_system', 'source_provided'):
                errors.append('rubric_source 无效')
    return errors


def validate_candidate(candidate: dict, *, check_formulas=True) -> dict:
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
    errors.extend(validate_question_type(candidate))
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
    if candidate.get('question_type','single_choice') == 'single_choice' and conclusion and conclusion[-1] != candidate.get("answer"):
        warnings.append("解析结论与答案不一致")
    if candidate.get("quality_status") == "approved":
        confirmation = candidate.get("review_confirmation")
        if (not isinstance(confirmation, dict) or confirmation.get("confirmed") is not True
                or not isinstance(confirmation.get("reviewer"), str) or not confirmation["reviewer"].strip()
                or candidate.get("annotation_status") != "confirmed"):
            errors.append("approved 缺少明确人工确认")
    if check_formulas:
        from services.math_normalizer import audit_question
        findings = audit_question(candidate)
        warnings.extend('formula_warning: '+i['field']+' '+i['issue'] for i in findings['issues'])
        if candidate.get('formula_status') in ('formula_warning','formula_manual_review','invalid'):
            warnings.append('formula_warning: 题目尚未通过公式审核')
    warnings = list(dict.fromkeys(warnings))
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "can_approve": not errors and not warnings and candidate.get("extraction_status") == "complete"}
