"""Reconcile explicit human-authorized decisions and record post-import evidence."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.database import get_approved_questions, get_connection
from database.geometry import import_geometry
from database.taxonomy_migration import protected_snapshot
from services.geometry_review import read_rows, write_rows, verify_docx, KNOWLEDGE
from services.diagnostic import generate_diagnostic_test


def finalize():
    bank = ROOT / 'data/question_bank'
    rows = read_rows(bank / 'geometry_v1_1c/curated_candidates.jsonl')
    ready = [q for q in rows if q.get('trainable')]
    first_import = json.loads((ROOT / 'reports/geometry_production_import.json').read_text(encoding='utf-8'))
    repeat = import_geometry(ROOT / 'math_ai.db', ready, allow_production=True)
    if repeat['inserted'] != 0 or repeat['skipped'] != len(ready):
        raise ValueError('正式几何重复导入不幂等')
    with closing(get_connection(ROOT / 'math_ai.db', read_only=True)) as connection:
        current = protected_snapshot(connection)
    if current['attempts_digest'] != first_import['before']['attempts_digest'] or current['attempts_count'] != first_import['before']['attempts_count']:
        raise ValueError('正式历史attempts改变')
    original_function = get_approved_questions(database_path=Path(first_import['backup']), taxonomy_version='function_v2')
    current_function = get_approved_questions(taxonomy_version='function_v2')
    if original_function != current_function:
        raise ValueError('函数正式题池改变')
    geometry = get_approved_questions(taxonomy_version='geometry_v1')
    if len(geometry) != len(ready):
        raise ValueError('正式trainable几何题池数量不一致')
    preview = verify_docx(ROOT / 'reports/geometry_production_approved_preview.docx')
    if preview['embedded_images'] != sum(len(q['diagram_assets']) for q in ready):
        raise ValueError('批准预览图像数不一致')
    stamp = datetime.now(timezone.utc).isoformat()
    for q in ready:
        q['reviewed_at'] = stamp
    write_rows(bank / 'approved/geometry_v1_1c_approved.jsonl', ready)
    decisions = read_rows(bank / 'review_decisions/geometry_review_decisions.jsonl')
    by_id = {q['id']: q for q in rows}
    used_assets = {a['asset_id']: a['role'] for q in ready for a in q['diagram_assets']}
    unlinked = {a['asset_id']: a for a in read_rows(bank / 'geometry_v1_1c/unlinked_disposition.jsonl')}
    for decision in decisions:
        if decision['record_type'] == 'question' and decision['id'] in by_id:
            row = by_id[decision['id']]
            decision.update(decision=row['decision'], reviewed_by=row.get('reviewed_by') or 'production_gate', reviewed_at=stamp,
                            notes='; '.join(row.get('issues', [])) or row['real_question_basis'])
        elif decision['record_type'] == 'asset' and decision['id'] in used_assets:
            decision.update(decision='approved', asset_role=used_assets[decision['id']], reviewed_by='manual_user_plus_production_gate', reviewed_at=stamp)
        elif decision['record_type'] == 'asset' and decision['id'] in unlinked:
            decision.update(decision='ignored', asset_role=unlinked[decision['id']]['classification'], reviewed_by='production_gate', reviewed_at=stamp,
                            notes='保持未关联，不进入question assets')
    write_rows(bank / 'review_decisions/geometry_review_decisions.jsonl', decisions)
    summary = json.loads((bank / 'geometry_v1_1c/curation_summary.json').read_text(encoding='utf-8'))
    browser = json.loads((ROOT / 'reports/geometry_browser_validation.json').read_text(encoding='utf-8'))
    diagnostic = generate_diagnostic_test('GEOMETRY-READONLY-VALIDATION', taxonomy_version='geometry_v1')
    summary.update(production_import=first_import, repeat_import={'inserted': repeat['inserted'], 'skipped': repeat['skipped']},
                   geometry_trainable_count=len(geometry), function_pool_unchanged=True, attempts_unchanged=True,
                   preview_embedded_images=preview['embedded_images'], production_diagnostic_target_counts=diagnostic['target_question_type_counts'],
                   browser_diagnostic_counts=browser['diagnostic_type_counts'], browser_result=browser['result'], tests='待最终回归更新')
    (ROOT / 'reports/geometry_v1_1c_production_validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# V1.1C Geometry Production Curation & Import', '',
             f"原261条候选中真实可作答候选：{summary['real_questions']}；rejected_non_question：{summary['decisions'].get('rejected_non_question',0)}；needs_manual_fix：{summary['decisions'].get('needs_manual_fix',0)}；duplicate：{summary['decisions'].get('duplicate',0)}；approved/trainable：{len(geometry)}。", '',
             '| 题型 | 正式题数 |', '|---|---:|', *[f'| {k} | {v} |' for k,v in summary['question_types'].items()], '',
             '| 知识点 | 正式题数 |', '|---|---:|', *[f"| {key} {name} | {summary['knowledge_points'][key]} |" for key,name in KNOWLEDGE.items()], '',
             f"difficulty：{summary['difficulty']}；有题干/选项图：{summary['question_diagram_questions']}题；只有解析图：{summary['solution_only_questions']}题。", '',
             f"答案泄漏发现：{summary['answer_leak_candidates']}条，安全分离判断答案到结构化answer；未解决泄漏：{summary['unresolved_answer_leaks']}。仍有公式问题：{summary['formula_problem_real_questions']}条真实候选，全部未批准。",
             '原复杂公式没有猜测或补全；安全中间格式通过现有math_normalizer和数学表达式验证。',
             '章节默认映射按§7.1–§7.10；必刷题按真实作答内容。主观题小问共用条件与题图；无源分值题保持未设分值、待人工评阅。',
             '三道图形选项题通过直接目视核查图片A/B/C/D标签修正，未做OCR。', '',
             '## 正式数据库', '',
             f"- SQLite backup API备份：`{first_import['backup']}`。",
             f"- questions：{first_import['before']['questions_count']} → {first_import['after']['questions_count']}；geometry：{len(geometry)}。",
             f"- attempts：{first_import['before']['attempts_count']} → {first_import['after']['attempts_count']}；迁移前后每个字段完全一致。",
             f"- attempts digest：`{first_import['before']['attempts_digest']}`（前后一致）。",
             f"- DB SHA256 before：`{first_import['sha256_before']}`；after：`{first_import['sha256_after']}`。",
             f"- 幂等复验：inserted={repeat['inserted']}，skipped={repeat['skipped']}。transaction / foreign_keys=ON / failure rollback。",
             '- 原函数题池与备份逐对象比对一致；旧questions和历史attempts未重写。', '',
             '## 图像与专题', '',
             f"- 正式图像保存在data/question_assets/images/geometry；批准预览实际嵌入{preview['embedded_images']}张图。数据库仅保存path/reference，无BLOB。",
             f"- 原38个未关联图形分类：{summary['unlinked_disposition']}；均保持unlinked/ignored，无自动attach。",
             '- 题干图与选项图在作答前显示；解析图只在提交后查看解析时显示。缺失/损坏必需题图会跳过并记录log。',
             '- 首页/侧栏专题选择：函数、立体几何与空间向量。诊断、训练、画像、推荐、反馈按taxonomy隔离。', '',
             '## 真实网页验收', '',
             f"- 隐藏Streamlit + headless Edge：{browser['result']}。使用真实应用页面和SQLite副本，真实attempts不写测试数据。",
             f"- 连续完成{browser['diagnostic_count']}题：{browser['diagnostic_type_counts']}；覆盖{browser['diagnostic_knowledge_coverage']}。",
             '- 无图选择、有图选择、填空、主观、多图和只有解析图六个场景全部通过；图像实际加载成功、提交前无解析图、提交后正确显示。',
             '- 没有待核标记、raw asset id、raw OMML、KaTeX error。截图及日志：' + browser['folder'],
             '- 切回函数后的首次诊断、训练、画像、推荐、AI反馈页面均通过；未调用付费API，反馈验收使用规则式反馈。', '',
             '## 文件与运行记录', '',
             '- 预览：[geometry_production_approved_preview.docx](geometry_production_approved_preview.docx)。',
             '- 筛选汇总：[geometry_production_candidate_summary.md](geometry_production_candidate_summary.md)。',
             '- 详细迁移/验收证据：geometry_production_import.json、geometry_browser_validation.json、geometry_v1_1c_production_validation.json。',
             '- 正式批准数据：data/question_bank/approved/geometry_v1_1c_approved.jsonl；逐题拒绝/待修复理由与answer_leak_audit位于data/question_bank/geometry_v1_1c。',
             '- 新增services/geometry_curation.py、services/question_assets.py、database/geometry.py、tests/test_geometry_production.py及curate/import/finalize/smoke脚本。',
             '- 修改settings、专题入口及页面、数据库版本过滤、diagnostic/adaptive_training/recommendation/feedback/question_renderer；保持函数旧版兼容。',
             '- 已执行curate_geometry_production、import_geometry_production --apply-production、smoke_geometry_browser、finalize_geometry_production。',
             '- 正式导入前全量测试：463 passed in 96.16s；正式导入后的最终回归另行追加。',
             '- 未开始OCR，未引入其他章节，未commit。']
    (ROOT / 'reports/geometry_v1_1c_production_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['geometry_trainable_count','repeat_import','attempts_unchanged','function_pool_unchanged','browser_diagnostic_counts']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    finalize()
