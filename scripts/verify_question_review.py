"""Offline gold-bank acceptance; every database is automatically temporary."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.database import get_connection, get_training_questions, record_attempt
from init_db import initialize_database
from services.feedback import build_feedback_context, build_rule_based_feedback
from services.mastery import calculate_student_mastery
from services.profile import build_profile_data
from services.question_importer import get_approved_questions, import_questions
from services.question_review import read_jsonl, ReviewSession
from services.question_validator import load_taxonomy, validate_candidate
from services.question_bank_sandbox import create_sandbox, bank_service_context, training_questions, sandbox_recommendation
from services.recommendation import generate_recommendation, recommend_questions
from scripts.review_question_batch import DEFAULT_BATCH, output_paths


def _legacy_rows(path):
    with closing(get_connection(path, read_only=True)) as connection:
        return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]
                for table in ("knowledge_points", "questions", "attempts")}


def verify_approved_batch(approved_path: Path) -> dict:
    """Exercise real services against a disposable v2 projection, not production migration."""
    candidates = read_jsonl(Path(approved_path))
    if any(row.get("quality_status") != "approved" or not validate_candidate(row)["can_approve"]
           for row in candidates):
        raise ValueError("批准导出文件含非 approved 或校验失败题。")
    taxonomy = load_taxonomy()
    with tempfile.TemporaryDirectory(prefix="math-ai-gold-") as directory:
        legacy = Path(directory) / "legacy.db"
        initialize_database(legacy)
        record_attempt("TEST_LEGACY", "Q001", "A", 0, 2.0, database_path=legacy)
        before = _legacy_rows(legacy)
        old_mastery = calculate_student_mastery("TEST_GOLD", database_path=legacy)
        old_recommendation = generate_recommendation("TEST_GOLD", database_path=legacy)
        result = import_questions(candidates, database_path=legacy)
        if result["errors"] or result["rejected"]:
            raise ValueError("批准题导入失败。")
        assert result["inserted"] == len({row["fingerprint"] for row in candidates})
        assert result["skipped"] == len(candidates) - result["inserted"]
        repeated = import_questions(candidates, database_path=legacy)
        assert repeated["inserted"] == 0 and not repeated["errors"]
        assert repeated["skipped"] == len(candidates)
        assert _legacy_rows(legacy) == before
        assert calculate_student_mastery("TEST_GOLD", database_path=legacy) == old_mastery
        assert generate_recommendation("TEST_GOLD", database_path=legacy) == old_recommendation
        # Reviewed and rejected variants must never enter the approved bank.
        unapproved = [{**row, "quality_status": status} for row in candidates for status in ("reviewed", "draft", "rejected")]
        refusal = import_questions(unapproved, database_path=legacy)
        assert refusal["inserted"] == 0 and refusal["rejected"] == len(unapproved)
        bank = [row for point in taxonomy["knowledge_points"]
                for row in get_approved_questions(point["id"], database_path=legacy)]
        assert {row["fingerprint"] for row in bank} == {row["fingerprint"] for row in candidates}
        assert all(row["source_file"] and row["source_locator"] and row["taxonomy_version"] == "function_v2" for row in bank)
        # Separate disposable projection: no old rows are rewritten, no real path is accepted.
        projection = Path(directory) / "v2_projection.db"
        create_sandbox(projection, bank)
        training = training_questions(projection)
        assert {row["id"] for row in training} == {row["id"] for row in bank}
        with bank_service_context(projection, "TEST_GOLD"):
            mastery = calculate_student_mastery("TEST_GOLD", database_path=projection)
            assert len(mastery) == 15 and all(row["mastery_score"] is None for row in mastery)
            profile = build_profile_data(mastery)
            assert profile["overview"]["total_attempts"] == 0
            recommendation = generate_recommendation("TEST_GOLD", database_path=projection)
            assert all(row["id"] in {item["id"] for item in bank} for row in recommendation["recommended_questions"])
            empty_points = [point["id"] for point in taxonomy["knowledge_points"]
                            if not get_approved_questions(point["id"], database_path=legacy)]
            for key in empty_points:
                assert recommend_questions("TEST_GOLD", key, database_path=projection) == []
            feedback = build_rule_based_feedback(build_feedback_context("TEST_GOLD", database_path=projection))
            assert "未评估" in feedback
            if bank:
                first = bank[0]
                record_attempt("TEST_EVIDENCE", first["id"], first["answer"], 1, 1.5, database_path=projection)
                evidence = calculate_student_mastery("TEST_EVIDENCE", database_path=projection)
                assert sum(row["attempt_count"] for row in evidence) == 1
                assert next(row for row in evidence if row["knowledge_point_id"] == first["primary_knowledge_point_id"])["attempt_count"] == 1
                assert all(row["attempt_count"] == 0 for row in evidence if row["knowledge_point_id"] in first["related_knowledge_point_ids"])
        recommendation_status = sandbox_recommendation("TEST_GOLD", projection)["status"]
        assert _legacy_rows(legacy) == before
        return {"approved_count": len(candidates), "inserted": result["inserted"],
                "inserted_on_repeat": repeated["inserted"],
                "skipped_on_repeat": repeated["skipped"], "unapproved_rejected": refusal["rejected"],
                "training_count": len(training), "empty_knowledge_points": empty_points,
                "recommendation_status": recommendation_status,
                "empty_bank_message": "暂无金标准题，请先完成人工审核。" if not bank else "部分知识点可能暂无金标准题。",
                "source_traceable": True, "legacy_unchanged": True,
                "preserved_legacy_attempt_count": len(before["attempts"]),
                "mastery_profile_recommendation_feedback": "PASS（临时15节点、approved-only 与题级前置适配）",
                "real_database_modified": False}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="批准题临时库验收，不写真实数据库，不调用 API")
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    args = parser.parse_args()
    paths = output_paths(args.batch)
    try:
        session = ReviewSession(args.batch, *paths)
        # Verification is read-only for all review artifacts.
        expected = [session.latest[row["id"]] for row in session.candidates
                    if row["id"] in session.latest and session.latest[row["id"]]["quality_status"] == "approved"]
        if read_jsonl(paths[1]) != expected:
            raise ValueError("批准文件与审核日志不一致，请运行 --prepare 重建导出。")
        print(json.dumps(verify_approved_batch(paths[1]), ensure_ascii=False, indent=2))
    except (OSError, ValueError, AssertionError) as error:
        print(f"临时库验收失败（{type(error).__name__}），真实数据库未被修改。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
