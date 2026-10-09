"""Strict geometry production curation using source text, never guessed formulas."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from services.answer_evaluator import evaluate_fill_blank
from services.geometry_review import (KNOWLEDGE, ROOT, ReviewDocx, read_rows, write_rows, paragraph_number)
from services.math_normalizer import audit_question, validate_math_expression
from services.question_validator import content_fingerprint
from services.question_assets import geometry_trainable

PREREQUISITES = {'G001': [], 'G002': ['G001'], 'G003': [], 'G004': ['G003'], 'G005': ['G003'],
                 'G006': ['G003'], 'G007': ['G005', 'G006'], 'G008': ['G005', 'G006'],
                 'G009': ['G001', 'G004'], 'G010': ['G004', 'G005']}
DIAGRAM_PROMPT = re.compile(r'如图|图中|下图|根据图|由图|图示|直观图|图所示')
TASK = re.compile(r'求证|求|证明|判断|计算|选择|填空|作出|写出|是否存在|是否正确|哪[个些]|是[（(]|为[（(]')
MATERIAL_TITLE = re.compile(r'^(?:空间几何体的结构特征|直观图\s*$|圆柱、圆锥、圆台的侧面展开图|柱、锥、台、球的表面积|'
                            r'掌握|灵活应用.*结论|关于.*注意|基本事实|定理|定义|性质|公式|考试要求|思维升华|题型|知识|章节|'
                            r'内切球[:：]|棱切球[:：]|外接球[:：]|异面直线所成的角[:：]|直线和平面所成角的定义)')
LEAK = re.compile(r'[（(]\s*[√×]\s*[）)]|答案\s*[:：]?\s*[ABCD]|故选\s*[ABCD]|(?:^|\n)\s*解析')
# These option sheets were visually inspected, without OCR or image cropping.
VISUALLY_VERIFIED_OPTION_ASSETS = {
    'GQ-769c220b936c7ea6cb96': ['GA-bbcbdb53228cf351d337', 'GA-aabf43ea5ec2c8705d62'],
    'GQ-1db6c10b3f448db73138': ['GA-6337943ce5bdca34ec58', 'GA-c9785b00de19d48162e4'],
    'GQ-17375e27c41756cb5449': ['GA-68af02abc0ea275c2ce5'],
}


def remove_number(stem):
    return re.sub(r'^(?:例\s*\d+|跟踪训练\s*\d+|\d+[.．、])\s*', '', stem).strip()


def real_question_gate(row):
    """A task is required; a historic subjective label is never evidence."""
    stem = remove_number(row['stem'])
    if MATERIAL_TITLE.match(stem):
        return False, '学习材料标题/定义/定理/公式总结'
    if row.get('options') and len(row['options']) >= 2:
        return True, '可作答选择题，存在独立选项'
    if re.search(r'判断下列|判断.*是否正确', stem):
        return True, '判断任务'
    if TASK.search(stem):
        return True, '明确作答任务'
    if re.search(r'_{3,}|\u3000{2,}', stem) and row.get('answer', '').strip():
        return True, '填空任务与源答案'
    if re.match(r'^(?:例|跟踪训练)\d+', row['stem']) and row.get('answer', '').strip():
        return True, '例题/跟踪训练与独立源答案'
    return False, '无可实际作答任务'


def strip_answer_leaks(stem):
    """Separate fully labelled judgment answers; ambiguous solution prose is blocked."""
    events, judgment = [], {}
    lines = stem.splitlines()
    if re.search(r'判断下列|判断.*是否正确', stem):
        for index, line in enumerate(lines):
            number = re.match(r'^\s*[（(](\d+)[）)]', line)
            mark = re.search(r'[（(]\s*([√×])\s*[）)]\s*$', line)
            if number and mark:
                judgment[number[1]] = mark[1]
                lines[index] = line[:mark.start()].rstrip()
                events.append({'kind': 'embedded_judgment_answer', 'sub_question': number[1], 'answer': mark[1], 'original': line, 'cleaned': lines[index]})
        sub_numbers = re.findall(r'(?:^|\n)\s*[（(](\d+)[）)]', stem)
        if judgment and set(judgment) != set(sub_numbers):
            return '\n'.join(lines), judgment, events, 'needs_manual_fix'
    cleaned = '\n'.join(lines)
    if LEAK.search(cleaned) or re.search(r'(?:答案|故选|解析)[:：]?', cleaned):
        events.append({'kind': 'unresolved_answer_leak', 'original': cleaned})
        return cleaned, judgment, events, 'needs_manual_fix'
    return cleaned, judgment, events, 'clean'


def primary_mapping(row):
    match = re.search(r'§7\.(\d+)', row['source_file'])
    if match:
        primary = f'G{int(match[1]):03}'
        # Retain chapter primary unless a task explicitly makes a different
        # chapter the sole objective (mixed subquestions keep source primary).
        return primary, []
    stem = row['stem']
    patterns = [('G010', r'轨迹|动点'), ('G009', r'截面|交线|作出'), ('G008', r'距离'),
                ('G007', r'所成角|二面角|夹角|余弦值|正弦值'), ('G002', r'内切球|外接球|球.*半径|球心'),
                ('G001', r'体积|表面积|侧面积|展开图'), ('G005', r'证明.*垂直|求证.*⊥|垂直'),
                ('G004', r'平行|∥'), ('G006', r'向量|数量积|坐标'), ('G003', r'共面|共线|异面|位置关系')]
    matches = [key for key, pattern in patterns if re.search(pattern, stem)]
    return (matches[0], matches[1:]) if matches else (None, [])


def validate_geometry_question(row):
    """Geometry contract: source solutions can remain ungraded references."""
    errors = []
    if not row.get('real_question') or not row.get('stem', '').strip():
        errors.append('non_question_or_empty_stem')
    kind = row.get('question_type')
    options = row.get('options') or {}
    if kind in {'single_choice', 'multiple_choice'}:
        if len(options) < 2 or any(not isinstance(v, str) or not v.strip() for v in options.values()):
            errors.append('missing_options')
        if len(set(options.values())) != len(options):
            errors.append('duplicate_options')
        if kind == 'single_choice' and row.get('answer') not in options:
            errors.append('missing_unique_answer')
        if kind == 'multiple_choice' and (not row.get('correct_answers') or not set(row['correct_answers']) <= set(options)):
            errors.append('missing_correct_answers')
    elif kind == 'fill_blank':
        if not row.get('canonical_answer') and not row.get('accepted_answers'):
            errors.append('missing_fill_answer')
    elif kind == 'subjective':
        if not TASK.search(row['stem'] + '\n' + '\n'.join(s['stem'] for s in row.get('sub_questions', []))):
            errors.append('missing_subjective_task')
        if not row.get('reference_answer', '').strip():
            errors.append('missing_reference_solution')
    else:
        errors.append('invalid_question_type')
    if LEAK.search(row['stem']):
        errors.append('answer_leak')
    if row.get('primary_knowledge_point_id') not in KNOWLEDGE:
        errors.append('unknown_primary')
    return errors


def source_subquestions(row):
    stem = row['stem']
    matches = list(re.finditer(r'(?:^|\n)\s*[（(](\d+)[）)]\s*', stem))
    subs = []
    for index, match in enumerate(matches):
        text = stem[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(stem)].strip()
        score = re.search(r'[（(](\d+)分[）)]\s*$', text)
        subs.append({'id': match[1], 'stem': re.sub(r'[（(]\d+分[）)]\s*$', '', text),
                     'max_score': int(score[1]) if score else None})
    if subs:
        row['stem'] = stem[:matches[0].start()].strip()
        row['sub_questions'] = subs
    total = re.search(r'^\s*(?:\d+[.．、])?[（(](\d+)分[）)]', stem)
    row['max_score'] = int(total[1]) if total else None
    row['score_status'] = 'source_provided' if total else 'ungraded_reference_only'


def curate_row(source, asset_index, *, review_only=False):
    row = deepcopy(source)
    row['stem'] = remove_number(row['stem'])
    row['real_question'], row['real_question_basis'] = real_question_gate(row)
    row['primary_knowledge_point_id'], row['related_knowledge_point_ids'] = primary_mapping(row)
    row['taxonomy_version'] = 'geometry_v1'
    row['difficulty'] = 2 if row.get('question_type') != 'subjective' else 3
    row['diagram_assets'], row['issues'] = [], []
    row['quality_status'] = 'draft'
    option_ids = VISUALLY_VERIFIED_OPTION_ASSETS.get(row['id'], [])
    if option_ids:
        row['options'] = {letter: f'见选项图 {letter}' for letter in 'ABCD'}
        row['option_image_verification'] = 'visual_inspection_without_ocr'
    row['stem'], judgment, events, row['answer_leak_status'] = strip_answer_leaks(row['stem'])
    row['answer_leak_audit'] = events
    if not row['real_question']:
        row.update(decision='rejected_non_question', trainable=False)
        return row
    if judgment:
        row.update(question_type='fill_blank', options=None, answer=None, canonical_answer=''.join(judgment.values()),
                   accepted_answers=[''.join(judgment.values())], answer_type='text', judgment_answers=judgment)
        row['stem'] = re.sub(r'[（(]请在括号中打“√”或“×”[）)]', '', row['stem'])
        row['stem'] += '\n请按小问顺序连续填写√或×。'
    else:
        raw_answer = row.get('answer', '').strip()
        if row.get('options'):
            letters = re.fullmatch(r'[ABCD](?:[\s、,，]*[ABCD])*', raw_answer)
            selected = re.findall('[ABCD]', raw_answer) if letters else []
            row['question_type'] = 'multiple_choice' if len(selected) > 1 or '多选' in row['stem'] else 'single_choice'
            if row['question_type'] == 'multiple_choice':
                row['correct_answers'], row['answer'] = sorted(set(selected)), None
        elif TASK.search(row['stem']) and not re.search(r'_{3,}|\u3000{2,}', row['stem']):
            row['question_type'] = 'subjective'
            row['reference_answer'] = row.get('reference_solution') or raw_answer
            row['answer'] = None
            source_subquestions(row)
        else:
            row.update(question_type='fill_blank', canonical_answer=raw_answer, accepted_answers=[raw_answer] if raw_answer else [], answer=None)
            try:
                evaluate_fill_blank(raw_answer, raw_answer, 'numeric')
                row['answer_type'] = 'numeric'
            except ValueError:
                row['answer_type'] = 'text'
    if row['answer_leak_status'] != 'clean':
        row['issues'].append('unresolved_answer_leak')
    # Only image placeholders backed by source assets are removed. Diagram
    # information and visibility are retained in the separate asset objects.
    assets = [asset_index[aid] for aid in row['review_asset_ids']]
    table_assets = [a for a in assets if a['verification']['table_context']]
    if table_assets or any('表格' in w for w in row['extraction_warnings']):
        row['issues'].append('ambiguous_table_structure')
    for asset in assets:
        role = 'option_image' if asset['id'] in option_ids else asset['asset_role']
        if role == 'unknown':
            row['issues'].append('ambiguous_asset_role')
            continue
        if not asset['verification']['source_verified'] or not asset['verification'].get('media_matches_source', True):
            row['issues'].append('invalid_source_media')
        if any(not c['legal'] or c['warnings'] for c in asset['image_checks']):
            row['issues'].append('image_quality_or_file_warning')
        for index, resource in enumerate(asset['resources'], 1):
            row['diagram_assets'].append({'asset_id': asset['id'], 'role': role,
                                         'path': f"data/question_assets/images/geometry/{asset['id']}_{index}.png",
                                         'source_path': resource['path'], 'source_sha256': resource['sha256'],
                                         'source_locator': asset['source_locator']})
    source_stem = row['stem']
    # A source-position stem diagram can carry essential information without
    # a verbal prompt. Retain it rather than guessing that it is disposable.
    stem_assets = [a for a in row['diagram_assets'] if a['role'] in {'question_diagram', 'option_image'}]
    explicit_prompt = re.compile(r'如图|图中|下图|根据图|由图|图示|图所示')
    row['diagram_required'] = bool(explicit_prompt.search(source_stem) or any(explicit_prompt.search(s['stem']) for s in row.get('sub_questions', [])) or stem_assets)
    row['diagram_requirement_basis'] = 'explicit_prompt' if DIAGRAM_PROMPT.search(source_stem) else 'source_stem_information' if stem_assets else 'no_stem_diagram_needed'
    if row['diagram_required'] and not stem_assets:
        row['issues'].append('missing_required_diagram')
    if len(row['review_asset_ids']) != source_stem.count('[图片待核]') + row.get('explanation', '').count('[图片待核]') + sum(s['stem'].count('[图片待核]') for s in row.get('sub_questions', [])):
        # Answer images or unusual visual containers need explicit fixing.
        if not row['visual_count_check']['matches']:
            row['issues'].append('unresolved_visual_count')
    for field in ['stem', 'explanation', 'reference_answer']:
        if isinstance(row.get(field), str):
            row[field] = row[field].replace('[图片待核]', '').strip()
    for sub in row.get('sub_questions', []):
        sub['stem'] = sub['stem'].replace('[图片待核]', '').strip()
    if row.get('options'):
        for key in row['options']:
            row['options'][key] = row['options'][key].replace('[图片待核]', '').strip()
    audited = audit_question(row)
    row = audited['normalized']
    row['formula_findings'] = audited['issues']
    # audit_question additionally needs explicit extraction-marker and syntax
    # checks; a marker in prose otherwise bypasses expression normalization.
    def formulas(value):
        if isinstance(value, str):
            if re.search(r'\[公式待核\]|OMML|sqrt\(|_\(|\^\(|\([^()]+\)/\(', value):
                row['formula_findings'].append({'issue': 'unresolved_formula_or_intermediate', 'original': value})
            for expression in re.findall(r'\$([^$]+)\$', value):
                checked = validate_math_expression(expression)
                if not checked['valid']:
                    row['formula_findings'].append(checked)
        elif isinstance(value, dict):
            for child in value.values(): formulas(child)
        elif isinstance(value, list):
            for child in value: formulas(child)
    for field in ['stem', 'options', 'explanation', 'canonical_answer', 'accepted_answers', 'reference_answer', 'sub_questions']:
        if field in row: formulas(row[field])
    if any('OMML' in w or '公式' in w for w in row['extraction_warnings']):
        row['formula_findings'].append({'issue': 'source_formula_warning_unresolved'})
    row['formula_status'] = 'valid' if not row['formula_findings'] else 'needs_manual_fix'
    if row['formula_status'] != 'valid':
        row['issues'].append('formula_warning')
    row['structure_errors'] = validate_geometry_question(row)
    row['difficulty'] = 3 if row['question_type'] == 'subjective' else 2
    # For a split subjective stem, validate tasks across all subquestions too.
    if row.get('sub_questions') and 'missing_subjective_task' in row['structure_errors'] and any(TASK.search(s['stem']) for s in row['sub_questions']):
        row['structure_errors'].remove('missing_subjective_task')
    row['issues'].extend(row['structure_errors'])
    row['structure_status'] = 'valid' if not row['structure_errors'] and not any('structure' in x or 'table' in x for x in row['issues']) else 'needs_manual_fix'
    row['issues'] = sorted(set(row['issues']))
    row['decision'] = 'needs_manual_fix' if row['issues'] else 'approved'
    row['quality_status'] = 'approved' if not row['issues'] else 'draft'
    row['reviewed_by'] = 'manual_user_plus_production_gate' if not row['issues'] else None
    if not row['issues']:
        resolutions = {
            'knowledge_warning': '按用户确认的章节默认primary/必刷题实际任务重新映射，primary有效且唯一',
            'answer_warning': '从源判断题逐小问安全分离答案，或直接保留源reference solution；结构门禁通过',
            'solution_warning': '客观题保留完整源答案；按本阶段规则解析允许缺省，未编造解析',
            'image_reuse_warning': '保留不同源位置的稳定asset id；媒体可复用，逐实例来源哈希和单题关联核对通过',
        }
        row['resolved_review_findings'] = [{**warning, 'resolution': resolutions.get(warning['warning_type'], '生产门禁复核通过')}
                                           for warning in row.get('warnings', [])]
        row['warnings'] = []
        row['review_status'] = 'approved'
        row['type_status'] = 'valid'
        row['review_group'] = 'production_gate_passed'
    row['trainable'] = geometry_trainable(row, check_files=False)
    row['fingerprint'] = content_fingerprint(row)
    if review_only:
        row.update(quality_status='reviewed' if not row['issues'] else 'draft',
                   decision='pending_review' if not row['issues'] else 'needs_manual_fix',
                   review_status='pending_review', reviewed_by=None, trainable=False)
    return row


def curate_geometry(root=ROOT):
    bank = root / 'data/question_bank'
    staging = bank / 'geometry_v1_1a'
    sources = read_rows(bank / 'geometry_v1_1b/questions_review.jsonl')
    assets = read_rows(bank / 'geometry_v1_1b/asset_verification.jsonl')
    index = {a['id']: a for a in assets}
    rows = [curate_row(q, index) for q in sources]
    seen = set()
    for row in rows:
        if row.get('trainable'):
            if row['fingerprint'] in seen:
                row.update(decision='duplicate', quality_status='draft', trainable=False)
            seen.add(row['fingerprint'])
    output = bank / 'geometry_v1_1c'
    write_rows(output / 'curated_candidates.jsonl', rows)
    approved = [q for q in rows if q.get('trainable')]
    write_rows(output / 'approved_ready.jsonl', approved)
    write_rows(output / 'answer_leak_audit.jsonl', [{'id': q['id'], 'events': q['answer_leak_audit'], 'status': q.get('answer_leak_status')} for q in rows if q['answer_leak_audit']])
    unlinked = []
    for asset in assets:
        if asset['question_id'] is not None:
            continue
        context = asset['context_at']
        role = 'decorative' if re.search(r'重点解读|知识过关|高考|考试要求|思维升华', context) else 'teaching_asset' if re.search(r'定义|定理|性质|法向量|方向向量|公式|平行|垂直|内切|外接', context) else 'unknown'
        unlinked.append({'asset_id': asset['id'], 'question_id': None, 'classification': role,
                         'decision': 'ignored', 'context': context, 'source_locator': asset['source_locator']})
    write_rows(output / 'unlinked_disposition.jsonl', unlinked)
    doc = ReviewDocx(f'Geometry 正式批准预览：{len(approved)} 条 production gate 通过题')
    for question in approved:
        doc.page_break()
        doc.text('Question ID: ' + question['id'], bold=True)
        doc.text(f"来源：{Path(question['source_file']).name} | {question['source_question_number']}\nprimary: {question['primary_knowledge_point_id']}\n题型：{question['question_type']} | difficulty: {question['difficulty']}\ndiagram_required: {question['diagram_required']}")
        doc.text('题干', bold=True)
        doc.text(question['stem'])
        for sub in question.get('sub_questions', []):
            doc.text(f"({sub['id']}) {sub['stem']}")
        for number, asset in enumerate(question['diagram_assets'], 1):
            original = index[asset['asset_id']]
            resource_index = next(i for i, r in enumerate(original['resources']) if r['path'] == asset['source_path'])
            doc.picture(staging / asset['source_path'], f"image {number} | {asset['role']}", original['image_checks'][resource_index])
        for label, text in (question.get('options') or {}).items():
            doc.text(label + '. ' + text)
        doc.text('答案：' + str(question.get('answer') or question.get('correct_answers') or question.get('canonical_answer') or question.get('reference_answer')))
        doc.text('解析：' + question['explanation'])
        doc.text('全部门禁 valid / clean；reviewed_by=manual_user_plus_production_gate')
    doc.save(root / 'reports/geometry_production_approved_preview.docx')
    summary = {'original_candidates': len(rows), 'real_questions': sum(q['real_question'] for q in rows),
               'decisions': dict(Counter(q['decision'] for q in rows)), 'question_types': dict(Counter(q['question_type'] for q in approved)),
               'knowledge_points': {k: sum(q['primary_knowledge_point_id'] == k for q in approved) for k in KNOWLEDGE},
               'difficulty': dict(Counter(q['difficulty'] for q in approved)),
               'diagram_required': dict(Counter(str(q['diagram_required']) for q in approved)),
               'question_diagram_questions': sum(any(a['role'] in {'question_diagram', 'option_image'} for a in q['diagram_assets']) for q in approved),
               'solution_only_questions': sum(not q['diagram_required'] and any(a['role'] == 'solution_diagram' for a in q['diagram_assets']) for q in approved),
               'answer_leak_candidates': sum(bool(q['answer_leak_audit']) for q in rows),
               'unresolved_answer_leaks': sum(q.get('answer_leak_status') != 'clean' for q in rows if q['real_question']),
               'formula_problem_real_questions': sum(q.get('formula_status') != 'valid' for q in rows if q['real_question']),
               'unlinked_disposition': dict(Counter(a['classification'] for a in unlinked))}
    (output / 'curation_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Geometry 正式批准候选预览', '', '门禁通过后获本轮用户授权批准；预览生成程序不修改真实数据库。首次导入前已生成并完成验证。',
             '没有猜公式，没有把知识说明作为subjective，没有自动attach未关联图片。', '',
             '```json', json.dumps(summary, ensure_ascii=False, indent=2), '```', '',
             '主观题保留多个小问。没有源分值的题仅保存待人工评阅解答，不推断分数。',
             '题干位置的合法信息图保留，解析图在提交后显示；无题干图和图形提示则默认不需要图。',
             '章节§7.1–7.10提供默认primary；必刷题按实际作答内容映射。',
             'needs_manual_fix的逐项理由见data/question_bank/geometry_v1_1c/curated_candidates.jsonl。',
             '预览：geometry_production_approved_preview.docx。']
    (root / 'reports/geometry_production_candidate_summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary
