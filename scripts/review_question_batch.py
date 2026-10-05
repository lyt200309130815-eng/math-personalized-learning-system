"""Human-only review CLI; immutable snapshot and separate progress files."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.question_review import CHECKLIST, ReviewSession
from services.question_validator import validate_candidate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = ROOT / "data/question_bank/candidates/function_batch_001.jsonl"


def output_paths(batch: Path) -> tuple[Path, Path, Path]:
    bank = batch.parent.parent if batch.parent.name == "candidates" else batch.parent
    reports = ROOT / "reports" if batch.resolve() == DEFAULT_BATCH.resolve() else bank / "reports"
    return (bank / "reviews" / f"{batch.stem}_review.jsonl",
            bank / "approved" / f"{batch.stem}_approved.jsonl",
            reports / f"question_review_{batch.stem.removeprefix('function_')}.md")


@contextmanager
def review_lock(path: Path):
    """Reject concurrent reviewers; do not silently remove another process's lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def display_candidate(candidate: dict) -> None:
    print("\n" + "=" * 60)
    for label, field in (("ID", "id"), ("原始来源", "source_file"), ("章节", "source_section"),
                         ("原题号", "source_question_number"), ("定位", "source_locator"), ("题干", "stem")):
        print(f"{label}：{candidate.get(field) or '原文未标注'}")
    for letter in "ABCD":
        print(f"{letter}：{candidate.get('options', {}).get(letter, '缺失')}")
    for label, field in (("标准答案", "answer"), ("解析", "explanation"),
                         ("主要知识点", "primary_knowledge_point_id"), ("相关知识点", "related_knowledge_point_ids"),
                         ("题级前置", "question_prerequisite_ids"), ("难度", "difficulty"),
                         ("能力标签", "ability_tags"), ("方法标签", "method_tags"),
                         ("预计用时（秒）", "estimated_time"), ("提取状态", "extraction_status"),
                         ("提取警告", "extraction_warnings"), ("fingerprint", "fingerprint")):
        print(f"{label}：{candidate.get(field)}")
    validation = validate_candidate(candidate)
    print("校验警告：", "; ".join(validation["errors"] + validation["warnings"]) or "无结构警告，仍须核对原文")
    print("需要人工确认：" + "；".join(CHECKLIST))


def review_batch(path: Path, *, input_fn=input, reviewer: str | None = None,
                 revisit_skipped: bool = False, prepare_only: bool = False,
                 reviews_path: Path | None = None, approved_path: Path | None = None,
                 report_path: Path | None = None) -> ReviewSession:
    defaults = output_paths(Path(path))
    paths = (reviews_path or defaults[0], approved_path or defaults[1], report_path or defaults[2])
    with review_lock(paths[0].with_suffix(".lock")):
        session = ReviewSession(path, *paths)
        session.save_outputs()
        if prepare_only:
            return session
        for candidate in session.pending(revisit_skipped=revisit_skipped):
            display_candidate(candidate)
            while True:
                choice = input_fn("a=approve / r=reject / s=skip / q=保存退出：").strip().lower()
                decision = {"a": "approve", "r": "reject", "s": "skip", "approve": "approve",
                            "reject": "reject", "skip": "skip"}.get(choice)
                if choice == "q":
                    session.save_outputs()
                    return session
                if decision is None:
                    print("请输入 a、r、s 或 q。")
                    continue
                if decision == "approve" and not validate_candidate(candidate)["can_approve"]:
                    print("校验未通过，不能批准；请 reject、skip 或退出。此版本不覆盖 warning。")
                    continue
                if not reviewer:
                    reviewer = input_fn("审核人：").strip()
                if not reviewer:
                    print("审核人不能为空。")
                    continue
                confirmed = False
                if decision == "approve":
                    confirmed = input_fn("已逐项核对原 DOCX 和数学 checklist？输入 confirm：").strip() == "confirm"
                    if not confirmed:
                        print("尚未明确确认，未批准。")
                        continue
                notes = input_fn("审核备注（可留空）：").strip()
                session.decide(candidate["id"], decision, reviewer, notes, confirmed=confirmed)
                break
        print("本轮审核完成。使用 --revisit-skipped 可再次检查跳过的题。")
        return session


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="逐题人工审核；候选快照不变，不写数据库")
    parser.add_argument("batch", nargs="?", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--reviewer", help="审核人姓名或标识")
    parser.add_argument("--revisit-skipped", action="store_true")
    parser.add_argument("--prepare", action="store_true", help="只生成空进度/统计，不进行人工审核")
    args = parser.parse_args()
    try:
        review_batch(args.batch, reviewer=args.reviewer, revisit_skipped=args.revisit_skipped,
                     prepare_only=args.prepare)
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as error:
        print(f"审核已停止（{type(error).__name__}）。已保存的决定会在下次运行恢复。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
