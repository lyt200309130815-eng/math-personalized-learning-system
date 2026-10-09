"""Deterministic, adaptive initial assessment without LLM calls."""
from collections import Counter
from contextlib import closing
import json
import math
import time
from uuid import uuid4

from database.database import get_connection, get_approved_questions, get_knowledge_points, get_question_prerequisites
from database.diagnostic import ensure_schema, load_latest, save_state
from services.mastery import calculate_student_mastery
from services.recommendation import generate_recommendation
from services.diagnostic_mix import plan_questions, TYPES
from services.answer_evaluator import evaluate_question, NeedsManualReview
from services.answer_attachments import save_answer_image
import logging
from settings import get_active_taxonomy_version

GROUPS = {
    'A 基础概念': ['K001', 'K002'],
    'B 函数性质': [f'K{i:03d}' for i in range(3, 7)],
    'C 基本初等函数': [f'K{i:03d}' for i in range(7, 12)],
    'D 函数综合应用': [f'K{i:03d}' for i in range(12, 16)],
}


def generate_diagnostic_test(student_id, taxonomy_version=None, max_questions=None, *, database_path=None):
    """Prepare a pool and first question; later questions depend on responses."""
    taxonomy_version = taxonomy_version or get_active_taxonomy_version()
    max_questions = max_questions if max_questions is not None else (15 if taxonomy_version == 'geometry_v1' else 18)
    if taxonomy_version not in ('function_v2', 'geometry_v1'):
        raise ValueError('首次函数诊断仅支持 function_v2。')
    if not isinstance(max_questions, int) or isinstance(max_questions, bool) or not 1 <= max_questions <= 20:
        raise ValueError('题量必须为1至20的整数。')
    if not student_id.strip():
        raise ValueError('学生编号不能为空。')
    points = get_knowledge_points(taxonomy_version, database_path=database_path)
    graph = {p['id']: json.loads(p['prerequisite_ids']) for p in points}
    mastery = calculate_student_mastery(student_id, database_path=database_path, taxonomy_version=taxonomy_version)
    pool = [q for q in get_approved_questions(database_path=database_path, taxonomy_version=taxonomy_version)
            if q['difficulty'] <= 3 and q.get('question_type', 'single_choice') in TYPES]
    with closing(get_connection(database_path, read_only=True)) as conn:
        recent_ids = [r[0] for r in conn.execute('SELECT question_id FROM attempts WHERE student_id=? ORDER BY id DESC LIMIT 30', (student_id,))]
    geometry_limits = []
    if taxonomy_version == 'geometry_v1':
        from services.adaptive_training import exposure_tokens
        identities = {q['id']: exposure_tokens(q) for q in pool}
        with closing(get_connection(database_path, read_only=True)) as conn:
            recent_ids += [r[0] for r in conn.execute('''SELECT s.question_id FROM training_session_questions s
                JOIN training_sessions t ON t.id=s.session_id WHERE t.student_id=?
                GROUP BY s.question_id ORDER BY MAX(s.selected_at) DESC LIMIT 30''', (student_id,))]
        exposed = set().union(*(identities.get(qid, {('id', qid)}) for qid in recent_ids)) if recent_ids else set()
        excluded_points = {q['knowledge_point_id'] for q in pool if exposure_tokens(q) & exposed}
        pool = [q for q in pool if not exposure_tokens(q) & exposed]
        unique_pool, seen_sources = [], set()
        for q in pool:
            if not exposure_tokens(q) & seen_sources:
                unique_pool.append(q)
                seen_sources.update(exposure_tokens(q))
        pool = unique_pool
        for key in sorted(excluded_points - {q['knowledge_point_id'] for q in pool}):
            geometry_limits.append(f'{key}可用原题近期已曝光，本轮不重复；证据不足 / 待进一步训练。')
    plan, mix, type_limits = plan_questions(pool, min(max_questions, len(pool)), recent_ids)
    logging.getLogger(__name__).info('Diagnostic question mix: %s', mix)
    extras = {q['id']: get_question_prerequisites(q['id'], taxonomy_version, database_path=database_path) for q in pool}
    limitations = [f"{p['name']}暂无难度1–3的已批准诊断题。" for p in points
                   if not any(q['knowledge_point_id'] == p['id'] for q in pool)]
    if len(pool) < max_questions:
        limitations.append(f'可用题仅{len(pool)}道，测评将提前结束。')
    limitations.extend(geometry_limits)
    if taxonomy_version == 'geometry_v1':
        for point in points:
            if sum(q['knowledge_point_id'] == point['id'] for q in pool) < 3:
                limitations.append(point['name'] + '独立诊断题不足3道，单次结果仅为探测；证据不足 / 待进一步训练。')
    state = dict(id=uuid4().hex, student_id=student_id, taxonomy_version=taxonomy_version,
                 max_questions=min(max_questions, len(pool)), pool=pool, graph=graph, extras=extras,
                 unevaluated=[p['knowledge_point_id'] for p in mastery if p['mastery_score'] is None],
                 coverage_limitations=limitations, answers=[], question_index=0, submitted=False,
                 planned_question_ids=plan, target_question_type_counts=mix,
                 mix_policy_version='V1.0D.3',
                 formula_policy_version='V1.0D.4',
                 type_coverage_limitation=type_limits, recent_question_ids=recent_ids,
                 diagnostic_started=True, diagnostic_completed=False, current_question=None, result=None)
    if taxonomy_version == 'geometry_v1':
        state['geometry_quality_policy'] = 'V1.1D'
    _advance(state)
    return state


def _next_question(state):
    """Two foundation probes, then breadth; repeated failures penalize descendants.

    Diagnostic probes can cross unverified prerequisites to measure coverage;
    practice recommendations still enforce the existing strict prerequisite rules.
    """
    used = {a['question_id'] for a in state['answers']}
    counts = Counter(a['knowledge_point_id'] for a in state['answers'])
    scored_counts = Counter(a['knowledge_point_id'] for a in state['answers'] if a['is_correct'] is not None)
    correct = Counter(a['knowledge_point_id'] for a in state['answers'] if a['is_correct'])
    failed = {key for key, count in scored_counts.items() if count >= 2 and correct[key] / count < .5}
    type_counts = Counter(a.get('question_type', 'single_choice') for a in state['answers'])
    def ancestors(key, trail=()):
        if key in trail:
            raise ValueError('知识点前置关系存在循环。')
        return set(state['graph'][key]).union(*(ancestors(p, trail + (key,)) for p in state['graph'][key]))
    def rank(q):
        key = q['knowledge_point_id']
        parents = ancestors(key) | set(state['extras'][q['id']])
        foundation = key in (('G001', 'G003') if state['taxonomy_version'] == 'geometry_v1' else ('K001', 'K002')) and counts[key] < 2
        return (0 if foundation else 1, counts[key] + .75 * len(parents & failed),
                key not in state['unevaluated'], len(parents),
                type_counts[q.get('question_type', 'single_choice')]/max(1, state.get('target_question_type_counts', {}).get(q.get('question_type', 'single_choice'), 1)), q['difficulty'] > 2,
                q['difficulty'], key, q['id'])
    planned = set(state.get('planned_question_ids', [q['id'] for q in state['pool']]))
    remaining = [q for q in state['pool'] if q['id'] not in used and q['id'] in planned]
    if state['taxonomy_version'] == 'geometry_v1':
        from services.adaptive_training import exposure_tokens
        used_tokens = set().union(*(exposure_tokens(q) for q in state['pool'] if q['id'] in used)) if used else set()
        remaining = [q for q in remaining if not exposure_tokens(q) & used_tokens]
    return min(remaining, key=rank) if remaining else None


def _advance(state):
    state['question_index'] = len(state['answers'])
    state['submitted'] = False
    state['current_question'] = _next_question(state) if len(state['answers']) < state['max_questions'] else None
    state['question_started_at'] = time.time()


def start_diagnostic(student_id, *, database_path=None, restart=False, max_questions=None, taxonomy_version=None):
    """Resume persisted progress unless a completed assessment is explicitly restarted."""
    taxonomy_version = taxonomy_version or get_active_taxonomy_version()
    previous = load_latest(student_id, database_path, taxonomy_version=taxonomy_version)
    if previous and (not previous['diagnostic_completed'] or not restart):
        return _upgrade_active(previous, database_path)
    state = generate_diagnostic_test(student_id, taxonomy_version=taxonomy_version, max_questions=max_questions, database_path=database_path)
    ensure_schema(database_path)
    with closing(get_connection(database_path)) as conn, conn:
        # Another tab may have started a session while the pool was being prepared.
        existing = conn.execute('''SELECT state_json FROM diagnostic_sessions
            WHERE student_id=? AND completed=0 AND taxonomy_version=? ''', (student_id, taxonomy_version)).fetchone()
        if existing:
            return json.loads(existing[0])
        conn.execute('INSERT INTO diagnostic_sessions(id,student_id,taxonomy_version,state_json) VALUES (?,?,?,?)',
                     (state['id'], student_id, taxonomy_version, json.dumps(state, ensure_ascii=False)))
    return _finish_if_needed(state, database_path)


def submit_diagnostic_answer(session_id, question_id, user_answer, *, database_path=None, answer_time=None, answer_payload=None):
    """Atomically save an attempt, its diagnostic link and next question exactly once."""
    if not isinstance(user_answer, str):
        raise ValueError('请填写答案后再提交。')
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT state_json FROM diagnostic_sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise ValueError('测评不存在。')
        state = json.loads(row[0])
        if any(a['question_id'] == question_id for a in state['answers']):
            return state
        q = state['current_question']
        if state['diagnostic_completed'] or not q or q['id'] != question_id:
            raise ValueError('当前题目已变化，请刷新页面。')
        approved = conn.execute('''SELECT 1 FROM question_knowledge_mappings
            WHERE taxonomy_version=? AND question_id=? AND role='primary' AND review_status='approved' ''', (state['taxonomy_version'], q['id'])).fetchone()
        if not approved:
            raise ValueError('题目已退出批准题库，请联系教师。')
        trainable = {row['id']:row for row in get_approved_questions(database_path=database_path,taxonomy_version=state['taxonomy_version'])}
        if q['id'] not in trainable:
            raise ValueError('题目公式需要修复，请刷新后自动跳过。')
        q = trainable[q['id']]
        elapsed = max(0., time.time() - state['question_started_at']) if answer_time is None else answer_time
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('作答时间无效。')
        kind = q.get('question_type', 'single_choice')
        if kind != 'subjective' and not user_answer.strip():
            raise ValueError('请填写答案后再提交。')
        payload = {'text': user_answer}
        if kind == 'subjective':
            image = (answer_payload or {}).get('image_bytes')
            if len(user_answer) > 20000 or (not user_answer.strip() and not image):
                raise ValueError('请填写解题过程或上传图片，文字不超过20000字。')
            if image:
                payload['attachment_path'] = save_answer_image(image, database_path=database_path)
        reason = None
        try:
            evaluated = evaluate_question(q, user_answer)
        except NeedsManualReview as error:
            evaluated = None; reason = str(error)
        correct = int(evaluated) if evaluated is not None else None
        cursor = conn.execute('''INSERT INTO attempts(student_id,question_id,user_answer,is_correct,answer_time,
            hint_count,retry_count) VALUES (?,?,?,?,?,0,0)''', (state['student_id'], q['id'], user_answer, correct, elapsed))
        conn.execute('INSERT INTO diagnostic_answers(session_id,question_id,attempt_id) VALUES (?,?,?)',
                     (session_id, q['id'], cursor.lastrowid))
        status = 'scored' if correct is not None else 'submitted_pending_review' if kind == 'subjective' else 'needs_manual_review'
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='attempt_details'").fetchone():
            conn.execute('INSERT INTO attempt_details VALUES (?,?,?,?,?,?,?)',
                         (cursor.lastrowid, kind, json.dumps(payload, ensure_ascii=False), payload.get('attachment_path'),
                          'scored' if correct is not None else 'pending', correct, q.get('max_score') if kind == 'subjective' else 1))
        if kind == 'subjective' and q.get('max_score'):
            conn.execute('''INSERT INTO subjective_submissions(student_id,question_id,attempt_id,text_answer,
                attachment_path,status,max_score) VALUES (?,?,?,?,?,?,?)''',
                         (state['student_id'], q['id'], cursor.lastrowid, user_answer, payload.get('attachment_path'), status, q['max_score']))
        if reason:
            conn.execute('INSERT INTO answer_review_requests(attempt_id,status,reason) VALUES (?,?,?)', (cursor.lastrowid, status, reason))
        state['answers'].append(dict(question_id=q['id'], knowledge_point_id=q['knowledge_point_id'],
                                    user_answer=user_answer, is_correct=correct, attempt_id=cursor.lastrowid,
                                    question_type=kind, submission_status=status, answer_payload=payload))
        _advance(state)
        save_state(conn, state)
    return _finish_if_needed(state, database_path)


def explain_profile(profile):
    """Keep limited evidence explicit even when a single answer has a high score."""
    sections = {name: [] for name in ('优势知识点', '需要巩固知识点', '证据不足知识点', '未评估知识点')}
    for p in profile:
        name, score = p['knowledge_point_name'], p['mastery_score']
        if p.get('evidence_status') == 'insufficient':
            sections['证据不足知识点'].append(name + '：证据不足 / 待进一步训练；需要更多独立原题验证。')
            continue
        if score is None:
            sections['未评估知识点'].append(name + '：尚未获得直接作答证据。')
            continue
        if p['attempt_count'] <= 2:
            sections['证据不足知识点'].append(name + '：证据较少，需进一步验证；一次错误不代表完全不会。')
        if score >= .8 and p['attempt_count'] >= 3:
            sections['优势知识点'].append(f'{name}当前掌握度约{score:.0%}。')
        elif score < .8:
            sections['需要巩固知识点'].append(f'{name}当前掌握度约{score:.0%}，建议优先进行基础巩固。')
    return sections


def _finish_if_needed(state, database_path):
    if state['current_question'] is not None or state['result'] is not None:
        return state
    profile = calculate_student_mastery(state['student_id'], database_path=database_path, taxonomy_version=state['taxonomy_version'])
    rec = generate_recommendation(state['student_id'], database_path=database_path, taxonomy_version=state['taxonomy_version'])
    state['diagnostic_completed'] = True
    scored = [a for a in state['answers'] if a['is_correct'] is not None]
    state['result'] = dict(total=len(state['answers']), correct=sum(a['is_correct'] for a in scored),
                           scored_total=len(scored), pending_subjective=sum(a.get('question_type') == 'subjective' and a['is_correct'] is None for a in state['answers']),
                           pending_fill_blank=sum(a.get('question_type') == 'fill_blank' and a['is_correct'] is None for a in state['answers']),
                           question_type_counts=dict(Counter(a.get('question_type', 'single_choice') for a in state['answers'])),
                           profile=profile, explanations=explain_profile(profile), recommendation=rec)
    tested = {a['knowledge_point_id'] for a in state['answers']}
    for p in profile:
        if p['knowledge_point_id'] not in tested:
            note = p['knowledge_point_name'] + '本轮未测试，保留未评估或已有历史证据。'
            if note not in state['coverage_limitations']:
                state['coverage_limitations'].append(note)
    with closing(get_connection(database_path)) as conn, conn:
        # Preserve the first completed snapshot if two tabs finish together.
        row = conn.execute('SELECT state_json FROM diagnostic_sessions WHERE id=? AND completed=1', (state['id'],)).fetchone()
        if row:
            return json.loads(row[0])
        save_state(conn, state)
    return state


def restore_diagnostic(student_id, *, database_path=None, taxonomy_version=None):
    state = load_latest(student_id, database_path, taxonomy_version=taxonomy_version)
    return _finish_if_needed(_upgrade_active(state, database_path), database_path) if state else None


def _upgrade_active(state, database_path):
    """Refresh legacy single-only pools while preserving every recorded answer."""
    if state['diagnostic_completed']:
        return state
    available = {q['id']:q for q in get_approved_questions(database_path=database_path,taxonomy_version=state['taxonomy_version'])}
    current = state.get('current_question')
    compatible = state.get('mix_policy_version') == 'V1.0D.3' and state.get('formula_policy_version') == 'V1.0D.4'
    if state['taxonomy_version'] == 'geometry_v1':
        compatible = compatible and state.get('geometry_quality_policy') == 'V1.1D'
    if compatible and (not current or current['id'] in available):
        if current:state['current_question'] = available[current['id']]
        return state
    if current and current['id'] not in available:
        logging.getLogger(__name__).warning('Diagnostic skipped untrainable formula question %s',current['id'])
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT state_json FROM diagnostic_sessions WHERE id=?',(state['id'],)).fetchone()
        if row:
            state = json.loads(row[0])
        if state['diagnostic_completed']:
            return state
        fresh = generate_diagnostic_test(state['student_id'], taxonomy_version=state['taxonomy_version'], max_questions=state['max_questions'], database_path=database_path)
        used = {a['question_id'] for a in state['answers']}
        pool = [q for q in fresh['pool'] if q['id'] not in used]
        planned, mix, limits = plan_questions(pool, min(state['max_questions']-len(state['answers']), len(pool)), fresh['recent_question_ids'], state['answers'])
        state.update(pool=fresh['pool'], extras=fresh['extras'], planned_question_ids=planned,
                     target_question_type_counts=dict(Counter(a.get('question_type','single_choice') for a in state['answers'])+Counter(mix)),
                     type_coverage_limitation=limits, mix_policy_version='V1.0D.3')
        state['formula_policy_version'] = 'V1.0D.4'
        if state['taxonomy_version'] == 'geometry_v1':
            state['geometry_quality_policy'] = 'V1.1D'
            state['coverage_limitations'] = fresh['coverage_limitations']
        _advance(state)
        save_state(conn,state)
    return state
