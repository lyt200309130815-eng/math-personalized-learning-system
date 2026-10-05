"""Shared synthetic question fixtures; never sourced from the real database."""

from services.question_validator import content_fingerprint


def candidate(**changes):
    result = {
        "id": "TEST-Q1", "stem": "函数 f(x)=2x+1，求 f(2) 的值。",
        "options": {"A": "1", "B": "3", "C": "5", "D": "7"},
        "answer": "C", "explanation": "代入 x=2，得到 f(2)=2×2+1=5，故选 C。",
        "taxonomy_version": "function_v2", "primary_knowledge_point_id": "K002",
        "related_knowledge_point_ids": [], "question_prerequisite_ids": [],
        "difficulty": 1, "ability_tags": ["calculation"], "method_tags": ["substitution"],
        "estimated_time": 60, "source_type": "docx", "source_file": "fixture.docx",
        "source_section": "函数表示", "source_question_number": "1.",
        "source_locator": "word/document.xml paragraphs 1–7", "extraction_status": "complete",
        "quality_status": "reviewed", "review_notes": [], "version": 1,
        "image_resources": [], "extraction_warnings": [], "annotation_status": "pending_review",
    }
    result.update(changes)
    result["fingerprint"] = content_fingerprint(result)
    return result


def approved(**changes):
    return candidate(quality_status="approved", annotation_status="confirmed",
                     review_confirmation={"reviewer": "测试审核人", "confirmed": True}, **changes)
