"""Offline, immutable Batch 002 selection; never opens a database or an API."""

import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.question_deduplication import DuplicateIndex
from services.question_review import atomic_write, read_jsonl
from services.question_validator import load_taxonomy, validate_candidate
from services.source_extractors.docx_question_extractor import extract_questions


def select_questions(rows, previous, annotations):
    """Explicit annotations are proposals, not mathematical approval."""
    old = DuplicateIndex(previous)
    selected_index = DuplicateIndex(previous)
    selected, pending, duplicates = [], [], []
    annotations = {row['id']: row for row in annotations}
    for original in rows:
        row = deepcopy(original)
        reasons = old.reasons(row)
        if reasons:
            duplicates.append({'id': row['id'], 'reasons': reasons,
                               'source_file': row['source_file'], 'source_locator': row['source_locator']})
            continue
        annotation = annotations.get(row['id'])
        if annotation:
            row.update({key: value for key, value in annotation.items()
                        if key not in {'id', 'annotation_reason'}})
            row['estimated_time'] = row['difficulty'] * 60
            row['review_notes'].append(annotation['annotation_reason'])
        checked = validate_candidate(row)
        if row['extraction_status'] != 'complete' or not checked['can_approve']:
            row['quality_status'] = 'draft'
            row['review_notes'].extend(checked['errors'] + checked['warnings'])
            pending.append(row)
        elif annotation and not selected_index.reasons(row):
            row['quality_status'] = 'reviewed'
            row['annotation_status'] = 'pending_teacher_review'
            row['question_type'] = 'single_choice'
            selected.append(row)
            selected_index.add(row)
    return selected, pending, duplicates


def projection_rows(approved, reviewed, knowledge_points):
    """Keep hypothetical counts separate from official approved counts."""
    result = []
    for point in knowledge_points:
        key = point['id']
        current = [row for row in approved if row['quality_status'] == 'approved'
                   and row['primary_knowledge_point_id'] == key]
        proposed = [row for row in reviewed if row['quality_status'] == 'reviewed'
                    and row['primary_knowledge_point_id'] == key]
        hypothetical = current + proposed
        covered = (len(hypothetical) >= 3
                   and any(row['difficulty'] in (1, 2) for row in hypothetical)
                   and any(row['difficulty'] in (2, 3) for row in hypothetical))
        result.append({'id': key, 'name': point['name'], 'current_approved': len(current),
                       'candidate_reviewed': len(proposed), 'projected_total': len(hypothetical),
                       'projected_status': 'sufficient_coverage' if covered else 'insufficient_coverage'})
    return result


def write_new_outputs(outputs):
    if any(path.exists() for path in outputs):
        raise FileExistsError('Batch 002 输出已存在，拒绝覆盖候选或审核快照。')
    for path, content in outputs.items():
        atomic_write(path, content)


def build_batch():
    # Keep paths relative: provenance IDs must be stable across machines.
    files = sorted(Path('data/raw_sources/function').glob('*.docx'))
    if len(files) != 15:
        raise ValueError('应存在15份原始 DOCX。')
    rows = []
    for path in files:
        extracted = extract_questions(path, max_candidates=500)
        if len(extracted) >= 500:
            raise ValueError('单文件提取上限已达到，需要重新检查扫描范围。')
        rows.extend(question.to_dict() for question in extracted)
    candidates = read_jsonl(Path('data/question_bank/candidates/function_batch_001.jsonl'))
    approved = read_jsonl(Path('data/question_bank/approved/function_batch_001_approved.jsonl'))
    annotations = json.loads(Path('data/question_bank/mappings/function_batch_002_annotations.json')
                             .read_text(encoding='utf-8'))['questions']
    missing = {row['id'] for row in annotations} - {row['id'] for row in rows}
    if missing:
        raise ValueError(f'定向标注的源题不再存在：{sorted(missing)}')
    selected, pending, duplicates = select_questions(rows, candidates + approved, annotations)
    points = load_taxonomy()['knowledge_points']
    projection = projection_rows(approved, selected, points)
    statuses = Counter(row['extraction_status'] for row in rows)
    excluded = Counter(row['extraction_status'] for row in pending)
    difficulties = Counter(row['difficulty'] for row in selected)
    abilities = Counter(tag for row in selected for tag in row['ability_tags'])
    methods = Counter(tag for row in selected for tag in row['method_tags'])
    report = ['# Batch 002 定向筛选报告', '',
              '本批仅生成 reviewed 候选，不代表数学审核通过；未批准、未导入数据库。', '',
              f'检查15份DOCX，识别单项选择题块 {len(rows)} 道（不含知识表、判断题、多选题和解答题）。',
              f'与 Batch 001 重复或同来源原题号冲突跳过 {len(duplicates)} 道；新识别 {len(rows)-len(duplicates)} 道。',
              f'最终 reviewed：{len(selected)}；新识别但需人工恢复的 draft：{len(pending)}。',
              '去重按来源和原题号采用保守规则；不同练习组重复编号可能被跳过，不宣称数学内容必然相同。',
              f'其余 {len(rows)-len(duplicates)-len(selected)-len(pending)} 道未入选，不属于本批定向清单。', '',
              '## 提取状态', '', '| 状态 | 全部扫描 | 新题待审排除 |', '|---|---:|---:|']
    for status in ('complete', 'formula_warning', 'image_required', 'incomplete', 'manual_review'):
        report.append(f'| {status} | {statuses[status]} | {excluded[status]} |')
    report += ['', '## 知识点分布', '', '| 知识点 | reviewed |', '|---|---:|']
    counts = Counter(row['primary_knowledge_point_id'] for row in selected)
    report += [f"| {p['id']} {p['name']} | {counts[p['id']]} |" for p in points]
    report += ['', '## 难度分布', '', '| difficulty | 数量 |', '|---|---:|']
    report += [f'| {difficulty} | {difficulties[difficulty]} |' for difficulty in range(1, 6)]
    for title, counts in (('ability_tag', abilities), ('method_tag', methods)):
        report += ['', f'## {title}', '', '| 标签 | 数量 |', '|---|---:|']
        report += [f'| {tag} | {count} |' for tag, count in sorted(counts.items())]
    report += ['', '## 仍然未满足的定向目标', '',
               'K007 找到0道可靠基础单选候选，无法达到至少3道目标。§2.5 顶点、对称轴基础内容主要为知识表和判断题；现有完整二次函数单选主要考查值域、单调性或最值，保持其真实 primary。图象缺失的题留在待审文件。',
               'K001、K008 的可靠新增分别少于3道，不转换多选/判断题，也不生成新题。需要补充原始单选资料或人工恢复待审题。', '',
               '## 原始来源（只读）', '']
    report += [f'- {path.as_posix()}' for path in files]
    report += ['', '## 重复跳过审计', '', '| ID | 依据 | 来源 / locator |', '|---|---|---|']
    report += [f"| {row['id']} | {', '.join(row['reasons'])} | {row['source_file']} / {row['source_locator']} |"
               for row in duplicates]
    report += ['', '## 待审排除明细', '', '| ID | 状态 | 来源 / locator |', '|---|---|---|']
    report += [f"| {row['id']} | {row['extraction_status']} | {row['source_file']} / {row['source_locator']} |"
               for row in pending]
    projected = ['# 函数题库覆盖预测', '',
                 'current_approved 仅计 Batch 001 已批准题；candidate_reviewed 是 Batch 002 待审核题，不能用于正式训练。projected_total 仅是假设未来全部批准的预测，不改变任何质量状态或掌握度。', '',
                 '门槛：每个知识点至少3题，并至少1道难度1–2、至少1道难度2–3；同一难度2题可满足两项难度条件。', '',
                 '| 知识点 | current_approved | candidate_reviewed | projected_total | 预测状态 |',
                 '|---|---:|---:|---:|---|']
    projected += [f"| {row['id']} {row['name']} | {row['current_approved']} | {row['candidate_reviewed']} | {row['projected_total']} | {row['projected_status']} |"
                  for row in projection]
    projected += ['', 'K007 仍无基础金标准候选，需补充可读原始资料。Batch 002 不会自动批准；正式 approved 总数仍为29。']
    def jsonl(values):
        return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in values)
    write_new_outputs({Path('data/question_bank/candidates/function_batch_002.jsonl'): jsonl(selected),
                       Path('data/question_bank/review_required/function_batch_002.jsonl'): jsonl(pending),
                       Path('reports/question_import_batch_002.md'): '\n'.join(report) + '\n',
                       Path('reports/question_bank_coverage_projection.md'): '\n'.join(projected) + '\n'})
    return {'inspected': len(rows), 'duplicate_skipped': len(duplicates), 'reviewed': len(selected),
            'excluded': dict(excluded), 'difficulty': dict(difficulties), 'projection': projection}


if __name__ == '__main__':
    print(json.dumps(build_batch(), ensure_ascii=True, indent=2))
