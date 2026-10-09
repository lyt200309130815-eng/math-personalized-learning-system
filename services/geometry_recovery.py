"""V1.1D: scoped source recovery and review artifacts; never production import."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from database.database import get_approved_questions, get_connection
from database.taxonomy_migration import protected_snapshot
from services.geometry_curation import curate_row, real_question_gate
from services.geometry_quality import classify_geometry_difficulty, source_fingerprint, DIFFICULTY_STANDARD
from services.geometry_review import KNOWLEDGE, ROOT, ReviewDocx, prepare_questions, read_rows, write_rows, verify_docx, paragraph_number, knowledge_suggestion, image_check
from services.question_validator import content_fingerprint
from services.source_extractors.geometry_math import read_geometry_blocks
from services.source_extractors.geometry_pipeline import scan_docx

SOLUTION_START = re.compile(r'^(?:(?:\([1-9]\)|（[1-9]）)\s*(?:解析|解|证明)(?:\s|$)|(?:解析|解|证明)(?:\s|[:：]|$))')
SECTION_END = re.compile(r'^三余弦定理.*的应用$|^思维升华|^方法总结|^成套的课件|^[一二三四五]、.*(?:选择题|填空题|解答题)')


def production_audit(database_path):
    """Count the actual approved/trainable pool with read-only connections."""
    rows = get_approved_questions(database_path=database_path, taxonomy_version='geometry_v1')
    with closing(get_connection(database_path, read_only=True)) as connection:
        counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                  for table in ('questions', 'attempts')}
        foreign_keys = [tuple(r) for r in connection.execute('PRAGMA foreign_key_check')]
    points = {}
    for key, name in KNOWLEDGE.items():
        pool = [r for r in rows if r['knowledge_point_id'] == key]
        kinds = Counter(r['question_type'] for r in pool)
        difficulty = Counter(r['difficulty'] for r in pool)
        points[key] = {'name': name, 'count': len(pool), 'types': dict(kinds),
                       'difficulty': dict(difficulty), 'gap_to_10': max(0, 10-len(pool)),
                       'choice_gap': max(0, 3-kinds['single_choice']-kinds['multiple_choice']),
                       'fill_gap': max(0, 2-kinds['fill_blank']), 'subjective_gap': max(0, 2-kinds['subjective']),
                       'missing_d2_d3_d4': [d for d in (2, 3, 4) if not difficulty[d]]}
    return {'database_counts': counts, 'geometry_trainable': len(rows), 'points': points,
            'types': dict(Counter(r['question_type'] for r in rows)),
            'difficulty': dict(Counter(r['difficulty'] for r in rows)),
            'foreign_key_violations': foreign_keys}, rows


def recover_source_row(original, blocks, assets):
    """Reparse exactly the original question span, preserving source image roles."""
    selected = [b for b in blocks if original['start_paragraph'] <= b['index'] <= original['end_paragraph']]
    raw = deepcopy(original)
    fields = dict(stem=[], answer=[], explanation=[])
    role = 'stem'
    transitions = []
    for block in selected:
        text = block['text']
        if re.match(r'^答案\s*[:：]?', text):
            role = 'answer'
        elif SOLUTION_START.match(text):
            role = 'explanation'
            transitions.append(block['index'])
        fields[role].append(text)
    raw.update({key: '\n'.join(value).strip() for key, value in fields.items()})
    raw['extraction_warnings'] = sorted({w for b in selected for w in b['warnings']})
    prepared = prepare_questions([raw], assets, {raw['source_file']: blocks})[0]
    # curate_row receives an independent strict parser's remaining warnings.
    prepared['extraction_warnings'] = raw['extraction_warnings']
    prepared['source_solution_start_paragraphs'] = transitions
    # Reconstruct precise field positions with the same boundary rule. The
    # legacy prepare_questions does not recognize numbered solution headings.
    role = 'stem'
    for block in selected:
        if re.match(r'^答案\s*[:：]?', block['text']):
            role = 'answer'
        elif SOLUTION_START.match(block['text']):
            role = 'explanation'
        prepared['paragraph_fields'][block['index']] = role
    return prepared


def recovered_primary(row):
    """Chapter drafts must not inflate G008 with angle-only exploration tasks."""
    task = row['stem'] + '\n' + '\n'.join(s['stem'] for s in row.get('sub_questions', []))
    options = '\n'.join((row.get('options') or {}).values())
    if row.get('primary_knowledge_point_id') == 'G008' and '距离' not in task + options:
        suggestion = knowledge_suggestion(task + '\n' + options)
        return suggestion['primary'], '§7.8也包含探索题，按实际任务而非章节标题标注；无距离任务不计G008。'
    if row.get('primary_knowledge_point_id') is None:
        text = task + '\n' + options
        if re.search(r'斜二测|直观图|平升|圆台|圆柱', text):
            return 'G001', '必刷题按直观图/体积/几何体任务标注。'
        suggestion = knowledge_suggestion(text)
        if suggestion['confidence'] != 'low':
            return suggestion['primary'], '必刷题根据原题选项所考性质标注，等待人工确认。'
        if '⊥' in options:
            return 'G005', '必刷题选项明确考查空间垂直关系，等待人工确认。'
        if '∥' in options:
            return 'G004', '必刷题选项明确考查空间平行关系，等待人工确认。'
    return row.get('primary_knowledge_point_id'), '保留原章节主知识点建议。'


def split_source_candidates(original, blocks, assets):
    """Split only explicit independent tasks after a completed source answer.

    This does not split the subquestions of a proof. Every child must still pass
    its own task, answer, formula and image gates; shared-condition references
    are withheld rather than filled from intuition.
    """
    selected = [b for b in blocks if original['start_paragraph'] <= b['index'] <= original['end_paragraph']]
    starts = [original['start_paragraph']]
    has_answer = False
    for block in selected:
        if re.match(r'^答案', block['text']):
            has_answer = True
        elif (has_answer and re.match(r'^(?:\s*[（(][1-9][）)]|典例\s+)', block['text'])
              and not SOLUTION_START.match(block['text'])):
            starts.append(block['index'])
            has_answer = False
    children = []
    for index, start in enumerate(starts):
        child = deepcopy(original)
        end = starts[index+1]-1 if index+1 < len(starts) else original['end_paragraph']
        boundary = next((b['index'] for b in selected if start < b['index'] <= end and SECTION_END.match(b['text'])), None)
        if boundary:
            end = boundary-1
        child['start_paragraph'], child['end_paragraph'] = start, end
        child['source_locator'] = f'word/document.xml paragraphs {start}–{end}'
        if start != original['start_paragraph']:
            child['id'] = 'GQ-' + hashlib.sha256((original['source_sha256'] + ':' + str(start)).encode()).hexdigest()[:20]
            child['source_question_number'] = original['source_question_number'] + f' / 独立练习{index+1}'
        if len(starts) > 1 or boundary:
            child['source_parent_id'] = original['id']
        selected_assets = []
        for asset in assets:
            if asset['question_id'] == original['id'] and start <= paragraph_number(asset)[0] <= end:
                assigned = deepcopy(asset)
                assigned['question_id'] = child['id']
                selected_assets.append(assigned)
        child['asset_ids'] = [a['id'] for a in selected_assets]
        children.append((child, selected_assets))
    return children


def build_recovery(root=ROOT, database_path=None):
    """Only read production; write V1.1D JSONL, audit and recovery Word."""
    root = Path(root)
    database_path = Path(database_path or root / 'math_ai.db').resolve()
    before_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()
    with closing(get_connection(database_path, read_only=True)) as connection:
        before_snapshot = protected_snapshot(connection)
    function_before = get_approved_questions(database_path=database_path, taxonomy_version='function_v2')
    audit, approved = production_audit(database_path)
    bank = root / 'data/question_bank'
    originals = read_rows(bank / 'geometry_v1_1b/questions_review.jsonl')
    pending = [r for r in read_rows(bank / 'geometry_v1_1c/curated_candidates.jsonl') if r['decision'] == 'needs_manual_fix']
    if len(pending) != 99:
        raise ValueError('Expected exactly 99 V1.1C needs_manual_fix records')
    original_by_id = {r['id']: r for r in originals}
    assets = read_rows(bank / 'geometry_v1_1b/asset_verification.jsonl')
    asset_index = {r['id']: r for r in assets}
    source_directory = root / 'data/raw_sources/geometry'
    files = sorted(source_directory.glob('*.docx'))
    if len(files) != 12:
        raise ValueError('Expected exactly 12 original DOCX files')
    scans = [scan_docx(p) for p in files]
    blocks = {p.name: read_geometry_blocks(p) for p in files}
    approved_fingerprints = {content_fingerprint(q) for q in approved}
    approved_sources = {source_fingerprint(q) for q in approved}
    results, recovered, seen = [], [], set()
    work = []
    for prior in pending:
        original = original_by_id[prior['id']]
        children = split_source_candidates(original, blocks[Path(original['source_file']).name], assets)
        for child, child_assets in children:
            work.append((prior, child, child_assets))
    for prior, original, scoped_assets in work:
        file = next(p for p in files if p.name == Path(original['source_file']).name)
        if hashlib.sha256(file.read_bytes()).hexdigest() != original['source_sha256']:
            raise ValueError('Source DOCX changed: ' + file.name)
        prepared = recover_source_row(original, blocks[file.name], scoped_assets)
        current_assets = {key: deepcopy(value) for key, value in asset_index.items()}
        current_assets.update({a['id']: deepcopy(a) for a in scoped_assets})
        asset_repairs = []
        for aid in prepared['review_asset_ids']:
            asset = current_assets[aid]
            paragraph, _ = paragraph_number(asset)
            role = prepared['paragraph_fields'].get(paragraph)
            target_role = ('solution_diagram' if role == 'explanation' else
                           ('option_image' if re.match(r'^\s*[ABCD][.．、]', asset['context_at']) else 'question_diagram')
                           if role == 'stem' else 'unknown')
            if target_role != asset['asset_role']:
                asset_repairs.append({'asset_id': aid, 'paragraph': paragraph,
                                      'before': asset['asset_role'], 'after': target_role})
                asset['asset_role'] = target_role
            # Reverify actual image bytes in this run, not just old metadata.
            asset['image_checks'] = [image_check(r, bank / 'geometry_v1_1a') for r in asset['resources']]
        row = curate_row(prepared, current_assets, review_only=True)
        if row.get('real_question'):
            row['primary_knowledge_point_id'], row['knowledge_recovery_basis'] = recovered_primary(row)
            if row['primary_knowledge_point_id']:
                row['issues'] = [x for x in row['issues'] if x != 'unknown_primary']
                row['structure_errors'] = [x for x in row['structure_errors'] if x != 'unknown_primary']
                if not row['structure_errors']:
                    row['structure_status'] = 'valid'
        row['asset_role_repairs'] = asset_repairs
        row['source_fingerprint'] = source_fingerprint(row)
        row['previous_issues'] = prior['issues']
        row['source_parent_id'] = prior['id']
        row['difficulty_review'] = classify_geometry_difficulty(row)
        row['difficulty'] = row['difficulty_review']['suggested']
        repairs = []
        if original.get('source_parent_id'):
            repairs.append('recoverable_structure')
        if asset_repairs:
            repairs.append('recoverable_asset')
        if 'formula_warning' in prior['issues'] and row.get('formula_status') == 'valid':
            repairs.append('recoverable_formula')
        if any(x != 'formula_warning' for x in prior['issues']) and not row.get('structure_errors'):
            repairs.append('recoverable_structure')
        if row.get('source_solution_start_paragraphs') and 'missing_reference_solution' in prior['issues'] and row.get('reference_answer'):
            repairs.append('recoverable_structure')
        row['repair_categories'] = sorted(set(repairs))
        row['repair_notes'] = []
        if original.get('source_parent_id'):
            row['repair_notes'].append('原候选合并了多个独立练习；依据明确小题起点与各自独立答案重新分段，逐段保留原条件与图形。')
        if 'recoverable_formula' in repairs:
            row['repair_notes'].append('从原DOCX完整OMML恢复向量箭头/分式/根式/矩阵及定界符；标准LaTeX校验通过，不推算表达式。')
        if 'recoverable_structure' in repairs:
            row['repair_notes'].append('按原段落识别带小问编号的证明/解/解析起点，分离题目任务与参考解答。')
        if asset_repairs:
            row['repair_notes'].append('依据独立练习/解析起点和原图段落位置恢复题图与解析图角色；解析图禁止作答前展示，未关联图形不绑定。')
        identity = content_fingerprint(row)
        duplicate = identity in approved_fingerprints or row['source_fingerprint'] in approved_sources or identity in seen
        if duplicate:
            row['issues'] = sorted(set(row.get('issues', []) + ['duplicate_existing_or_recovered']))
        if original.get('source_parent_id') and re.search(r'由上题|上一题|上述条件|同上|在\([1-9]\)的条件下', row['stem']):
            row['issues'].append('shared_conditions_require_manual_review')
        if not row.get('real_question'):
            row['recovery_class'] = 'non_question'
        elif row.get('issues'):
            row['recovery_class'] = 'still_ambiguous'
        else:
            row['recovery_class'] = ('recoverable_structure' if 'recoverable_structure' in repairs else
                                     'recoverable_asset' if 'recoverable_asset' in repairs else 'recoverable_formula')
            row.update(quality_status='reviewed', review_status='pending_review', decision='pending_review',
                       trainable=False, recovery_ready=True)
            recovered.append(row)
            seen.add(identity)
        row['fingerprint'] = identity
        row['recovery_ready'] = row in recovered
        results.append(row)
    output = bank / 'geometry_v1_1d'
    grouped = []
    for prior in pending:
        children = [r for r in results if r['source_parent_id'] == prior['id']]
        real_children = [q for q in children if q['recovery_class'] != 'non_question']
        complete = bool(real_children) and all(q['recovery_ready'] for q in real_children)
        group_class = ('recoverable_structure' if len(children) > 1 else children[0]['recovery_class']) if complete else 'still_ambiguous' if real_children else 'non_question'
        grouped.append({'id': prior['id'], 'previous_issues': prior['issues'], 'recovery_class': group_class,
                        'fully_recovered': complete, 'recovered_question_ids': [q['id'] for q in children if q['recovery_ready']],
                        'remaining_question_ids': [q['id'] for q in real_children if not q['recovery_ready']],
                        'excluded_non_question_ids': [q['id'] for q in children if q['recovery_class'] == 'non_question'],
                        'issues': sorted({x for q in children if not q['recovery_ready'] for x in q.get('issues', [])})})
    write_rows(output / 'recovery_analysis.jsonl', grouped)
    write_rows(output / 'recovery_question_details.jsonl', results)
    write_rows(output / 'geometry_recovery_batch_001.jsonl', recovered)
    write_rows(output / 'approved_difficulty_proposals.jsonl', [dict(id=q['id'], current_difficulty=q['difficulty'],
        source_fingerprint=source_fingerprint(q), proposal=classify_geometry_difficulty(q)) for q in approved])
    (output / 'source_scan.json').write_text(json.dumps(scans, ensure_ascii=False, indent=2), encoding='utf-8')
    doc = ReviewDocx('V1.1D 立体几何恢复批次001：仅本轮成功恢复题')
    for q in recovered:
        doc.page_break()
        doc.text('题目ID：' + q['id'], bold=True)
        doc.text(f"知识点：{q['primary_knowledge_point_id']} {KNOWLEDGE[q['primary_knowledge_point_id']]}\n题型：{q['question_type']}\n建议难度：D{q['difficulty']}（待人工确认）\n来源：{Path(q['source_file']).name}\n原题编号：{q['source_question_number']}\n定位：{q['source_locator']}\nsource_fingerprint：{q['source_fingerprint']}")
        doc.text('修复内容：' + '；'.join(q['repair_notes']))
        doc.text('难度依据：' + json.dumps(q['difficulty_review'], ensure_ascii=False))
        doc.text('题干', bold=True)
        doc.text(q['stem'])
        for sub in q.get('sub_questions', []):
            doc.text(f"({sub['id']}) {sub['stem']}")
        for role in ('question_diagram', 'option_image'):
            for a in q['diagram_assets']:
                if a['role'] == role:
                    original_asset = asset_index[a['asset_id']]
                    index = next(i for i, r in enumerate(original_asset['resources']) if r['path'] == a['source_path'])
                    doc.picture(bank / 'geometry_v1_1a' / a['source_path'], role, original_asset['image_checks'][index])
        for letter, text in (q.get('options') or {}).items():
            doc.text(letter + '. ' + text)
        doc.text('答案：' + str(q.get('answer') or q.get('correct_answers') or q.get('canonical_answer') or q.get('reference_answer')))
        doc.text('解析', bold=True)
        doc.text(q['explanation'] or '原资料无独立解析段落，保留原参考解答；不补写。')
        for a in q['diagram_assets']:
            if a['role'] == 'solution_diagram':
                original_asset = asset_index[a['asset_id']]
                index = next(i for i, r in enumerate(original_asset['resources']) if r['path'] == a['source_path'])
                doc.picture(bank / 'geometry_v1_1a' / a['source_path'], 'solution_diagram（仅解析区）', original_asset['image_checks'][index])
        doc.text('原DOCX数学段落（保留原生公式供核对）', bold=True)
        source_file = root / q['source_file'] if not Path(q['source_file']).is_absolute() else Path(q['source_file'])
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        from services.source_extractors.docx_question_extractor import W
        with ZipFile(source_file) as archive:
            paragraphs = list(ET.fromstring(archive.read('word/document.xml')).find(W + 'body').iter(W + 'p'))
            for paragraph in paragraphs[q['start_paragraph']-1:q['end_paragraph']]:
                doc.native_source(paragraph, preserve_scripts=True)
        doc.text('quality_status=reviewed；未批准、未导入，等待用户人工确认。')
    word = root / 'reports/geometry_recovery_batch_001_可读版.docx'
    doc.save(word)
    word_check = verify_docx(word)
    with closing(get_connection(database_path, read_only=True)) as connection:
        after_snapshot = protected_snapshot(connection)
    function_after = get_approved_questions(database_path=database_path, taxonomy_version='function_v2')
    if before_snapshot != after_snapshot or function_before != function_after:
        raise ValueError('Live database changed during recovery; rerun the read-only audit without deleting student records')
    baseline = [r for r in after_snapshot['rows']['attempts'] if r[0] <= 79]
    baseline_digest = hashlib.sha256(json.dumps(baseline, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    first_import = json.loads((root / 'reports/geometry_production_import.json').read_text(encoding='utf-8'))
    if len(baseline) != 79 or baseline_digest != first_import['before']['attempts_digest']:
        raise ValueError('Original 79 attempts changed')
    summary = {'input_pending': len(pending), 'recovered': len(recovered),
               'fully_recovered_source_candidates': sum(q['fully_recovered'] for q in grouped),
               'partially_recovered_source_candidates': sum(bool(q['recovered_question_ids']) and not q['fully_recovered'] for q in grouped),
               'classes': {key: sum(q['recovery_class'] == key for q in grouped) for key in
                           ('recoverable_formula', 'recoverable_structure', 'recoverable_asset', 'still_ambiguous', 'non_question')},
               'expanded_source_questions': len(results),
               'excluded_non_question_fragments': sum(q['recovery_class'] == 'non_question' for q in results),
               'repair_categories': dict(Counter(k for q in recovered for k in q['repair_categories'])),
               'types': dict(Counter(q['question_type'] for q in recovered)),
               'points': {key: sum(q['primary_knowledge_point_id'] == key for q in recovered) for key in KNOWLEDGE},
               'difficulty': dict(Counter(q['difficulty'] for q in recovered)),
               'unresolved_reasons': dict(Counter(issue for q in results if not q['recovery_ready'] for issue in q.get('issues', []))),
               'production_db_modified': False, 'production_sha256_before': before_hash,
               'production_sha256_after': hashlib.sha256(database_path.read_bytes()).hexdigest(), 'word': str(word),
               'database_access': 'read_only', 'production_attempts_before': before_snapshot['attempts_count'],
               'production_attempts_after': after_snapshot['attempts_count'],
               'production_attempts_digest_before': before_snapshot['attempts_digest'],
               'production_attempts_digest_after': after_snapshot['attempts_digest'],
               'original_79_attempts_unchanged': True, 'function_pool_unchanged': True,
               'word_verification': word_check, 'production_audit': audit}
    if summary['production_sha256_after'] != before_hash:
        raise ValueError('Production DB bytes changed during read-only recovery')
    (output / 'recovery_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    write_audit(root, audit)
    return summary


def write_audit(root, audit):
    lines = ['# V1.1D 正式题库覆盖审计', '', '从正式SQLite以mode=ro读取；只统计approved且通过公式、结构与题图门禁的trainable题。',
             f"正式总题数：{audit['database_counts']['questions']}；历史attempts：{audit['database_counts']['attempts']}；geometry_v1：{audit['geometry_trainable']}。", '',
             '| 知识点 | 数量 | 单选 | 多选 | 填空 | 主观 | D1/D2/D3/D4/D5 | 距10题缺口 |', '|---|---:|---:|---:|---:|---:|---|---:|']
    for key, p in audit['points'].items():
        lines.append(f"| {key} {p['name']} | {p['count']} | " + ' | '.join(str(p['types'].get(k, 0)) for k in ('single_choice','multiple_choice','fill_blank','subjective')) +
                     ' | ' + '/'.join(str(p['difficulty'].get(d, 0)) for d in range(1,6)) + f" | {p['gap_to_10']} |")
    lines += ['', '题型合计：' + json.dumps(audit['types'], ensure_ascii=False), '难度合计：' + json.dumps(audit['difficulty'], ensure_ascii=False), '',
              'V1.1C基线与本阶段初查为79条attempts；期间运行中的S001练习页面新增作答，当前数量如上。原79条逐字段摘要保持，本轮没有向正式库写入测试作答或删除新增记录。', '',
              'G008仅1题，距8–10题目标还缺7–9题；G006/G007/G010各8题。D2高度集中，D1/D4/D5为空。',
              '长期目标：各知识点至少10题；尽量选择类≥3、填空≥2，适合的高阶知识点主观≥2；G006–G010尽量覆盖D2/D3/D4。', '',
              '## 难度标准与校准', '', 'V1.1C按客观题D2、主观题D3统一赋值，属于保守题型占位。正式库本轮不改；逐题提案另存approved_difficulty_proposals.jsonl供后续确认。']
    lines += [f'- D{level}：{description}' for level, description in DIFFICULTY_STANDARD.items()]
    lines += ['', '每条提案包含源解答推理步骤数、任务与方法证据；不按数量目标机械升档。恢复题同样只是待审建议。',
              '审核恢复题后才可计算潜在覆盖；待审题当前不是trainable，也不进入选题。']
    (Path(root) / 'reports/geometry_v1_1d_coverage_audit.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
