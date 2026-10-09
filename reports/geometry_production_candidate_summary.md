# Geometry 正式批准候选预览

门禁通过后获本轮用户授权批准；预览生成程序不修改真实数据库。首次导入前已生成并完成验证。
没有猜公式，没有把知识说明作为subjective，没有自动attach未关联图片。

```json
{
  "original_candidates": 261,
  "real_questions": 222,
  "decisions": {
    "needs_manual_fix": 99,
    "approved": 123,
    "rejected_non_question": 39
  },
  "question_types": {
    "single_choice": 60,
    "multiple_choice": 23,
    "fill_blank": 26,
    "subjective": 14
  },
  "knowledge_points": {
    "G001": 14,
    "G002": 14,
    "G003": 19,
    "G004": 21,
    "G005": 18,
    "G006": 8,
    "G007": 8,
    "G008": 1,
    "G009": 12,
    "G010": 8
  },
  "difficulty": {
    "2": 109,
    "3": 14
  },
  "diagram_required": {
    "True": 45,
    "False": 78
  },
  "question_diagram_questions": 45,
  "solution_only_questions": 35,
  "answer_leak_candidates": 7,
  "unresolved_answer_leaks": 0,
  "formula_problem_real_questions": 82,
  "unlinked_disposition": {
    "decorative": 20,
    "unknown": 18
  }
}
```

主观题保留多个小问。没有源分值的题仅保存待人工评阅解答，不推断分数。
题干位置的合法信息图保留，解析图在提交后显示；无题干图和图形提示则默认不需要图。
章节§7.1–7.10提供默认primary；必刷题按实际作答内容映射。
needs_manual_fix的逐项理由见data/question_bank/geometry_v1_1c/curated_candidates.jsonl。
预览：geometry_production_approved_preview.docx。
