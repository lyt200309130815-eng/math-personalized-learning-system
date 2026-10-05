"""Build only batch_001: bounded inspection, candidate JSONL, Markdown report."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.source_extractors.docx_question_extractor import extract_questions
from services.question_validator import validate_candidate


def build_batch(source_directory: Path, output_directory: Path, report_path: Path, limit=30):
    """Scan at most 12 candidate choices/file; choose up to 30 diverse complete items."""
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("第一批 limit 必须为1–30整数")
    if not source_directory.is_dir():
        raise FileNotFoundError("原始 DOCX 目录不存在")
    batch_path = output_directory / "function_batch_001.jsonl"
    if batch_path.exists():
        raise FileExistsError("batch_001 已存在，拒绝覆盖人工审核结果")
    files = sorted(p for p in source_directory.glob("*.docx") if not p.name.startswith("~$"))
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    inspected, source_errors = [], []
    for path in files:
        try:
            inspected.extend(candidate.to_dict() for candidate in extract_questions(path, max_candidates=12))
        except (OSError, ValueError, KeyError, BadZipFile, ParseError) as error:
            source_errors.append(f"{path.name}：{type(error).__name__}")
    complete = [candidate for candidate in inspected if candidate["extraction_status"] == "complete"
                and validate_candidate(candidate)["can_approve"]]
    selected, seen = [], set()
    groups = defaultdict(list)
    for candidate in complete:
        groups[candidate["primary_knowledge_point_id"]].append(candidate)
    # Round-robin across knowledge points; shortest intact questions first.
    for values in groups.values():
        values.sort(key=lambda candidate: (len(candidate["stem"]) + len(candidate["explanation"]), candidate["id"]))
    while len(selected) < limit and any(groups.values()):
        for key in sorted(groups):
            while groups[key]:
                candidate = groups[key].pop(0)
                if candidate["fingerprint"] not in seen:
                    seen.add(candidate["fingerprint"])
                    selected.append(candidate)
                    break
            if len(selected) == limit: break
    output_directory.mkdir(parents=True, exist_ok=True)
    batch_path.write_text("".join(json.dumps(candidate, ensure_ascii=False) + "\n" for candidate in selected), encoding="utf-8")
    excluded = [candidate for candidate in inspected if candidate["extraction_status"] != "complete"]
    rejected_path = output_directory.parent / "review_required" / "function_batch_001.jsonl"
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.write_text("".join(json.dumps(candidate, ensure_ascii=False) + "\n" for candidate in excluded), encoding="utf-8")
    for path, digest in originals.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, "原资料发生变化"
    statuses = Counter(candidate["extraction_status"] for candidate in inspected)
    knowledge = Counter(candidate["primary_knowledge_point_id"] for candidate in selected)
    difficulty = Counter(candidate["difficulty"] for candidate in selected)
    lines = ["# 第一批函数题候选导入报告", "", "## 范围与状态", "",
             "只读取原 DOCX；每文件最多检查12个选择题候选，不代表全书题目总量。跳过 Word ~$ 临时锁文件；未处理第二批。",
             "complete 表示提取完整性检查通过，不表示答案已由数学求解器证明。知识点、标签、难度为待教师核实草标。",
             "本批可靠候选均为 reviewed，批准数为0；正式批准必须逐题核对原文、答案与解析。原始题号未知时为 null，不编造页码。",
             "", f"已读取 DOCX：{len(files)}；识别候选：{len(inspected)}；完整性通过：{len(complete)}；进入 batch_001：{len(selected)}。", "",
             "| extraction_status | 数量 |", "| --- | --- |"]
    for status in ("complete", "formula_warning", "image_required", "incomplete", "manual_review"):
        lines.append(f"| {status} | {statuses[status]} |")
    lines += ["", "## batch_001 分布", "", "| 知识点 | 数量 |", "| --- | --- |"]
    for i in range(1, 16): lines.append(f"| K{i:03} | {knowledge[f'K{i:03}']} |")
    lines += ["", "| difficulty | 数量 |", "| --- | --- |"]
    for i in range(1, 6): lines.append(f"| {i} | {difficulty[i]} |")
    lines += ["", "## 原始资料", ""] + [f"- {path.name}" for path in files]
    lines += ["", "## 未进入可靠批次的题目", "",
              "详情保存在 `data/question_bank/review_required/function_batch_001.jsonl`；图片只记录内部资源引用，不伪造图象。",
              "", "| 候选ID | 来源及定位 | 状态 | 原因 |", "| --- | --- | --- | --- |"]
    for candidate in excluded:
        reason = "; ".join(candidate["review_notes"][1:]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {candidate['id']} | {Path(candidate['source_file']).name} / {candidate['source_locator']} | {candidate['extraction_status']} | {reason} |")
    if source_errors: lines += ["", "## 文件读取错误", ""] + source_errors
    lines += ["", "## 导入与兼容边界", "",
              "本次没有批准或导入真实题目。approved-only 导入器在显式指定的隔离库中维护 function_v2 题库表，禁止真实 math_ai.db。",
              "旧训练、mastery、recommendation、feedback 继续使用旧 questions，不读取候选题，也不把新 K005 奇偶性解释为旧参数题。",
              "v2 审批题库提供 approved-only 查询边界；正式接入页面与推荐、启用15节点需另行完成 V0.8A 迁移验收，不在此批次自动切换。", ""]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {"inspected": len(inspected), "selected": len(selected), "statuses": dict(statuses),
            "knowledge": dict(knowledge), "difficulty": dict(difficulty)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="第一批候选提取，不写数据库")
    parser.add_argument("--source", type=Path, default=Path("data/raw_sources/function"))
    args = parser.parse_args()
    print(json.dumps(build_batch(args.source, Path("data/question_bank/candidates"),
                                Path("reports/question_import_batch_001.md")), ensure_ascii=False))
