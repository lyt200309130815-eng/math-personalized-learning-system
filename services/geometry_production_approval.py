"""V1.1E manual approval, independent final gates and production integration."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from PIL import Image

from database.database import DATABASE_PATH, get_connection, get_approved_questions
from database.taxonomy_migration import protected_snapshot
from services.geometry_curation import KNOWLEDGE, validate_geometry_question, LEAK
from services.geometry_quality import source_fingerprint
from services.geometry_review import ROOT, read_rows, write_rows, file_hash, verify_docx
from services.math_normalizer import audit_question, validate_math_expression
from services.question_validator import content_fingerprint
from services.question_assets import asset_path

BATCH = ROOT / 'data/question_bank/geometry_v1_1d/geometry_recovery_batch_001.jsonl'
OUTPUT = ROOT / 'data/question_bank/geometry_v1_1e'
NOTES = '用户已完成人工审核，确认恢复题无问题。'
UNRECOVERABLE = 'GQ-50a2466ead939ff28bd5'


def baseline(path):
    """Read the current logical baseline; never assume a historical attempt count."""
    with closing(get_connection(path, read_only=True)) as conn:
        snapshot = protected_snapshot(conn)
        geometry = conn.execute("SELECT COUNT(DISTINCT question_id) FROM question_sources WHERE taxonomy_version='geometry_v1'").fetchone()[0]
    return dict(database=str(Path(path).resolve()), db_sha256=file_hash(path),
                questions_count=snapshot['questions_count'], geometry_question_count=geometry,
                attempts_count=snapshot['attempts_count'], attempts_digest=snapshot['attempts_digest']), snapshot


def load_geometry_rows(conn):
    """Include all formal geometry rows, even those blocked from today's practice pool."""
    result = []
    for record in conn.execute("SELECT q.*,s.source_file,s.locator AS source_locator,s.fingerprint FROM questions q JOIN question_sources s ON s.question_id=q.id WHERE s.taxonomy_version='geometry_v1'"):
        q = dict(record)
        q['options'] = json.loads(q['options']) if q['options'] else None
        details = conn.execute('SELECT * FROM question_details WHERE question_id=?', (q['id'],)).fetchone()
        if details:
            q.update(dict(details))
            if q.get('accepted_answers'):
                q['accepted_answers'] = json.loads(q['accepted_answers'])
        extension = conn.execute('SELECT payload FROM question_type_extensions WHERE question_id=?', (q['id'],)).fetchone()
        if extension:
            q.update(json.loads(extension[0]))
        q['source_fingerprint'] = source_fingerprint(q)
        result.append(q)
    return result


def text_identity(q, normalized=False):
    """Compare the whole student task, including options and all subquestions."""
    task = [q.get('stem',''), q.get('options'), q.get('sub_questions')]
    if normalized:
        def normalize(value):
            if isinstance(value,str):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value))
            if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
            if isinstance(value,list):return [normalize(v) for v in value]
            return value
        task=normalize(task)
    value = json.dumps(task, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


def duplicate_audit(rows, existing, *, allow_identical=False):
    fields = ('question_id','exact_text','normalized_text','source_fingerprint','variant_fingerprint')
    def keys(q):
        return (q['id'], text_identity(q), text_identity(q, True), source_fingerprint(q),
                q.get('variant_fingerprint') or q.get('fingerprint') or content_fingerprint(q))
    indexes = {field: {} for field in fields}
    existing_by_id = {q['id']: q for q in existing}
    for q in existing:
        for field, value in zip(fields, keys(q)):
            if value:
                indexes[field].setdefault(value, set()).add(q['id'])
    result = []
    for q in rows:
        duplicates = {field: sorted(indexes[field].get(value, set()))
                      for field, value in zip(fields, keys(q)) if value and indexes[field].get(value)}
        prior = existing_by_id.get(q['id'])
        same = bool(allow_identical and prior and prior.get('fingerprint') == q.get('fingerprint')
                    and text_identity(prior) == text_identity(q)
                    and prior['difficulty'] == q['difficulty'] and source_fingerprint(prior) == source_fingerprint(q)
                    and prior.get('primary_knowledge_point_id') == q.get('primary_knowledge_point_id'))
        result.append(dict(id=q['id'], duplicates=duplicates, already_integrated=same))
        for field, value in zip(fields, keys(q)):
            if value:
                indexes[field].setdefault(value, set()).add(q['id'])
    return result


def production_gate(q, known_points=KNOWLEDGE):
    """Revalidate content, source bytes and image bytes rather than trusting statuses."""
    errors = list(validate_geometry_question(q))
    for field, required in [('real_question',True), ('structure_status','valid'),
                            ('formula_status','valid'), ('answer_leak_status','clean'),
                            ('review_status','approved'), ('taxonomy_version','geometry_v1')]:
        if q.get(field) != required:
            errors.append('invalid_' + field)
    if q.get('primary_knowledge_point_id') not in known_points:
        errors.append('primary_not_in_catalog')
    if type(q.get('difficulty')) is not int or not 1 <= q['difficulty'] <= 5:
        errors.append('invalid_difficulty')
    if q.get('issues') or q.get('warnings'):
        errors.append('unresolved_issues_or_warnings')
    if q.get('fingerprint') != content_fingerprint(q):
        errors.append('content_fingerprint_mismatch')
    sf = q.get('source_fingerprint')
    if not isinstance(sf,str) or not re.fullmatch('[0-9a-f]{64}', sf) or sf != source_fingerprint(q):
        errors.append('invalid_source_fingerprint')
    source = (ROOT / q.get('source_file','')).resolve()
    try:
        if (ROOT/'data/raw_sources/geometry').resolve() not in source.parents or file_hash(source) != q.get('source_sha256'):
            errors.append('invalid_source_file_or_hash')
    except OSError:
        errors.append('missing_source_file')
    kind = q.get('question_type')
    if kind == 'multiple_choice':
        answers = q.get('correct_answers')
        if not isinstance(answers,list) or len(answers)<2 or len(set(answers)) != len(answers) or q.get('answer') is not None:
            errors.append('invalid_multiple_answer_set')
    errors.extend('formula_audit:' + str(item) for item in audit_question(q)['issues'])
    def check_text(value):
        if isinstance(value,str):
            if re.search(r'OMML|oMath|sqrt\(|_\(|\^\(|\([^()]+\)/\(|\[公式待核\]|\$\$', value):
                errors.append('raw_or_unresolved_formula')
            for expression in re.findall(r'\$([^$]+)\$', value):
                if not validate_math_expression(expression)['valid']:
                    errors.append('invalid_math_expression')
        elif isinstance(value,dict):
            for child in value.values(): check_text(child)
        elif isinstance(value,list):
            for child in value: check_text(child)
    for field in ('stem','options','sub_questions','explanation','canonical_answer','accepted_answers','reference_answer'):
        check_text(q.get(field))
    for value in [q['stem']] + list((q.get('options') or {}).values()) + [s['stem'] for s in q.get('sub_questions',[])]:
        if LEAK.search(value): errors.append('answer_leak_recheck')
    diagrams = q.get('diagram_assets',[])
    if q.get('diagram_required') and not any(a['role']=='question_diagram' for a in diagrams):
        errors.append('missing_required_question_diagram')
    for a in diagrams:
        if a.get('role') not in ('question_diagram','option_image','solution_diagram'):
            errors.append('invalid_asset_role')
        try:
            asset_path(a)  # Validate the destination before any asset copy.
            image = (ROOT/'data/question_bank/geometry_v1_1a'/a['source_path']).resolve()
            if (ROOT/'data/question_bank/geometry_v1_1a').resolve() not in image.parents or file_hash(image)!=a['source_sha256']:
                errors.append('invalid_asset_hash')
            with Image.open(image) as img: img.verify()
            paragraph = int(a['source_locator'].split('paragraph ')[1].split()[0])
            role = q['paragraph_fields'][str(paragraph)]
            if (role=='explanation') != (a['role']=='solution_diagram'):
                errors.append('asset_role_leak')
        except (OSError,KeyError,ValueError,IndexError):
            errors.append('invalid_or_missing_asset')
    return sorted(set(errors))


def prepare_approval(rows, existing, known_points=KNOWLEDGE):
    reviewed = deepcopy(rows)
    if any(q['id']==UNRECOVERABLE for q in reviewed):
        raise ValueError('不可恢复特殊字体题不得纳入本次批准包')
    for q in reviewed:
        q.update(review_status='approved',reviewed_by='manual_user',review_notes=NOTES,trainable=False)
        remaining = []
        for warning in q.get('warnings',[]):
            if (warning.get('warning_type')=='knowledge_warning' and warning.get('warning_field')=='primary'
                    and q.get('primary_knowledge_point_id') in known_points):
                q.setdefault('resolved_review_findings',[]).append({**warning,
                    'resolution':'本批人工审核包已包含该primary；用户确认通过，最终catalog存在性与单primary字段复核有效。'})
            else:
                remaining.append(warning)
        q['warnings'] = remaining
    duplicates = duplicate_audit(reviewed, existing, allow_identical=True)
    for q, audit in zip(reviewed, duplicates):
        reasons = production_gate(q,known_points)
        if audit['duplicates'] and not audit['already_integrated']:
            reasons += ['duplicate:' + field for field in audit['duplicates']]
        q.update(production_gate_status='blocked' if reasons else 'valid', production_gate_reasons=reasons,
                 decision='approved_but_blocked' if reasons else 'approved',
                 quality_status='reviewed' if reasons else 'approved',trainable=not reasons)
    return reviewed, duplicates


def integrate(path=DATABASE_PATH, *, allow_production=False, output=OUTPUT):
    """Persist authorized review results and safely import only independently valid rows."""
    from database.geometry import import_geometry
    path = Path(path).resolve()
    before, snapshot = baseline(path)
    rows = read_rows(BATCH)
    if len(rows)!=113 or len({q['id'] for q in rows})!=113:
        raise ValueError('人工审核批次必须为113道独立题')
    word = verify_docx(ROOT/'reports/geometry_recovery_batch_001_可读版.docx')
    with closing(get_connection(path,read_only=True)) as conn:
        existing = load_geometry_rows(conn)
        known = {r[0] for r in conn.execute("SELECT id FROM knowledge_catalog WHERE taxonomy_version='geometry_v1'")}
    reviewed, duplicates = prepare_approval(rows,existing,known)
    output = Path(output)
    if (output/'migration_result.json').exists():
        # Preserve the first production baseline and its pre-import backup forever.
        output = output/'reruns'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True,exist_ok=True)
    write_rows(output/'manual_approval.jsonl',reviewed)
    write_rows(output/'duplicate_audit.jsonl',duplicates)
    ready = [q for q in reviewed if q['trainable']]
    write_rows(output/'approved_ready.jsonl',ready)
    (output/'production_baseline.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
    result = import_geometry(path,ready,allow_production=allow_production,migration_id='v1_1e_geometry_recovery',
                             backup_prefix='math_ai_pre_geometry_v1_1e_',review_records=reviewed,expected_baseline=snapshot)
    after,_ = baseline(path)
    if before['attempts_count']!=after['attempts_count'] or before['attempts_digest']!=after['attempts_digest']:
        raise ValueError('导入后学生作答发生变化；保留真实数据并调查，不恢复旧备份')
    result.update(baseline_before=before,baseline_after=after,manual_reviewed=len(reviewed),
                  gate_passed=len(ready),blocked=[dict(id=q['id'],reasons=q['production_gate_reasons']) for q in reviewed if not q['trainable']],
                  duplicate_count=sum(bool(a['duplicates']) and not a['already_integrated'] for a in duplicates),
                  duplicate_audit=duplicates,unrecoverable_status='needs_manual_fix',word_verification=word)
    (output/'migration_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
