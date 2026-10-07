"""Transparent next-question decisions using existing mastery and recommendation."""
from contextlib import closing
import json
import math
import time
import re
import logging
from collections import Counter
from uuid import uuid4

from database.database import get_connection, get_approved_questions, get_recent_attempts
from database.training_sessions import migrate_training_sessions, load_session, save_session
from database.multi_type import migrate_multi_type
from services.answer_evaluator import evaluate_question, NeedsManualReview
from services.answer_attachments import save_answer_image
from services.question_type_policy import question_type_ratios, select_question_type
from services.question_validator import validate_question_type
from services.question_variation import create_runtime_question, validate_variant
from services.mastery import calculate_knowledge_mastery
from services.recommendation import generate_recommendation, recommend_next_knowledge, recommend_questions

COVERAGE_MESSAGE = '当前知识点适合你的新题暂时不足，系统建议调整训练目标。'


def exposure_tokens(question):
    """Track IDs, content/variant identity and overlapping original paragraphs."""
    tokens={('id',question['id'])}
    for field in ('source_fingerprint','variant_fingerprint'):
        if question.get(field):tokens.add((field,question[field]))
    file=question.get('source_file');locator=question.get('source_locator','') or ''
    ranges=question.get('source_ranges')
    if not ranges:
        match=re.search(r'paragraphs (\d+)–(\d+)',locator)
        ranges=[[int(match[1]),int(match[2])]] if match else []
    if file:
        for begin,end in ranges:
            if end-begin<=500:
                tokens.update(('source_paragraph',file,n) for n in range(begin,end+1))
    return tokens


def initial_difficulty(mastery):
    score = mastery['mastery_score']
    if score is None or score < .4:
        return 1
    if score < .8:
        return 2
    return 3 if score < .9 else 4


def difficulty_band(difficulty):
    """A nearby level is permitted; actual question difficulty is logged separately."""
    return [max(1, difficulty - 1), min(5, difficulty + 1)]


def _kwargs(database_path):
    return dict(database_path=database_path, taxonomy_version='function_v2')


def _target(student_id, key, database_path):
    return recommend_next_knowledge(student_id, knowledge_point_id=key, **_kwargs(database_path))


def start_training_session(student_id, taxonomy_version='function_v2', *,
                           target_knowledge_point_id=None, database_path=None, lock_target=False):
    """Create/resume one active session; only recommendation chooses/resolves goals."""
    if taxonomy_version != 'function_v2' or not student_id.strip():
        raise ValueError('自适应训练需要有效学生编号和函数新知识体系。')
    migrate_multi_type(database_path)
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        existing = conn.execute("SELECT id FROM training_sessions WHERE student_id=? AND taxonomy_version=? AND status='active'",
                                (student_id, taxonomy_version)).fetchone()
        if existing and not lock_target:
            return load_session(conn, existing['id'], student_id)
        if lock_target and target_knowledge_point_id is None:
            raise ValueError('推荐训练必须指定知识点。')
        target = (_target(student_id, target_knowledge_point_id, database_path) if target_knowledge_point_id else
                  generate_recommendation(student_id, **_kwargs(database_path))['target_knowledge'])
        if lock_target and target['knowledge_point_id'] != target_knowledge_point_id:
            raise ValueError('学情已变化，请刷新推荐后再开始训练。')
        if existing:
            previous = load_session(conn, existing['id'], student_id)
            if previous['target_knowledge_point_id'] == target_knowledge_point_id:
                return previous
            previous['final_mastery'] = calculate_knowledge_mastery(
                student_id, previous['target_knowledge_point_id'], **_kwargs(database_path))['mastery_score']
            _stop(previous, 'user_ended', '你已选择切换到推荐学习目标，原训练记录已保留。')
            save_session(conn, previous)
        state = dict(id=uuid4().hex, student_id=student_id, taxonomy_version=taxonomy_version,
                     target_knowledge_point_id=target['knowledge_point_id'], target_name=target['knowledge_point_name'],
                     requested_target=target_knowledge_point_id, target_reason=target['reason'],
                     initial_mastery=target['mastery_score'], final_mastery=target['mastery_score'],
                     status='active', difficulty=min(initial_difficulty(target), _difficulty_cap(target)), answers=[], current_question=None,
                     submitted=False, correct_streak=0, wrong_streak=0, difficulty_changes=[],
                     decision_notes=[], stop_reason=None, next_target=None, max_questions=8)
        state['type_coverage_limitation'] = []
        state['question_type_counts'] = dict.fromkeys(('single_choice', 'multiple_choice', 'fill_blank', 'subjective'), 0)
        conn.execute('''INSERT INTO training_sessions(id,student_id,taxonomy_version,target_knowledge_point_id,
            initial_mastery,final_mastery,state_json) VALUES (?,?,?,?,?,?,?)''',
            (state['id'], student_id, taxonomy_version, state['target_knowledge_point_id'],
             state['initial_mastery'], state['final_mastery'], json.dumps(state, ensure_ascii=False)))
    return state


def get_training_session(student_id, session_id, *, database_path=None):
    with closing(get_connection(database_path, read_only=True)) as conn:
        return load_session(conn, session_id, student_id)


def _stop(state, status, reason, next_target=None):
    state.update(status=status, stop_reason=reason, next_target=next_target)


def _eligible(state, database_path):
    previews = recommend_questions(state['student_id'], state['target_knowledge_point_id'],
                                  limit=10000, **_kwargs(database_path))
    allowed = {q['id'] for q in previews}
    with closing(get_connection(database_path,read_only=True)) as conn:
        templates = set()
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='question_templates'").fetchone():
            templates = {r[0] for r in conn.execute("SELECT template_id FROM question_templates WHERE quality_status='approved' AND version='1'")}
    return [q for q in get_approved_questions(state['target_knowledge_point_id'], **_kwargs(database_path))
            if q['id'] in allowed and not validate_question_type(q) and (q.get('source_type') != 'generated_template'
                or (q.get('template_id') in templates and validate_variant(q)))]


def get_next_question(student_id, session_id, *, database_path=None):
    """Select only on explicit next; reruns return the same unanswered question.

    Priority: not in session, prerequisite eligible, not recently practiced,
    requested difficulty then nearby difficulty, stable question-ID tie break.
    """
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = load_session(conn, session_id, student_id)
        if state['status'] != 'active':
            return None
        target = _target(student_id, state['target_knowledge_point_id'], database_path)
        if target['knowledge_point_id'] != state['target_knowledge_point_id']:
            _stop(state, 'prerequisite_blocked', target['reason'], target)
            save_session(conn, state)
            return None
        eligible = _eligible(state, database_path)
        current = state['current_question']
        if current and not state['submitted'] and any(q['id'] == current['id'] for q in eligible):
            return current
        used = {row[0] for row in conn.execute('SELECT question_id FROM training_session_questions WHERE session_id=?', (session_id,))}
        mastery = calculate_knowledge_mastery(student_id, state['target_knowledge_point_id'], **_kwargs(database_path))
        cap = _difficulty_cap(mastery)
        ratios = question_type_ratios(mastery['mastery_score'])
        remaining = [q for q in eligible if q['id'] not in used
                     and q['difficulty'] <= cap and ratios.get(q.get('question_type','single_choice'), ratios['single_choice'])>0]
        history = list(conn.execute('SELECT question_id,MAX(id) AS last_id FROM attempts WHERE student_id=? GROUP BY question_id ORDER BY last_id DESC LIMIT 30', (student_id,)))
        recent = {r['question_id'] for r in history}
        ever_seen = {r[0] for r in conn.execute('SELECT DISTINCT question_id FROM attempts WHERE student_id=?', (student_id,))}
        ever_seen.update(r[0] for r in conn.execute('''SELECT DISTINCT s.question_id
            FROM training_session_questions s JOIN training_sessions t ON t.id=s.session_id
            WHERE t.student_id=?''', (student_id,)))
        recent.update(r[0] for r in conn.execute('''SELECT s.question_id
            FROM training_session_questions s JOIN training_sessions t ON t.id=s.session_id
            WHERE t.student_id=? GROUP BY s.question_id
            ORDER BY MAX(s.selected_at) DESC LIMIT 30''', (student_id,)))
        identities={q['id']:exposure_tokens(q) for q in get_approved_questions(**_kwargs(database_path))}
        def keys(ids):
            return set().union(*(identities.get(qid,{('id',qid)}) for qid in ids)) if ids else set()
        used_keys=keys(used);recent_keys=keys(recent);ever_keys=keys(ever_seen)
        remaining=[q for q in remaining if not exposure_tokens(q)&used_keys]
        if not any(not exposure_tokens(q)&recent_keys for q in remaining) and cap == 2 and mastery['attempt_count'] >= 2 and (mastery['mastery_score'] or 0) >= .4:
            # An exhausted basic pool may use its adjacent D3 level. This is
            # a question fallback, not an increase caused by a pending answer.
            adjacent = [q for q in eligible if q['id'] not in used and q['difficulty'] == 3
                        and not exposure_tokens(q)&(used_keys|recent_keys)]
            remaining.extend(adjacent)
            if adjacent:
                state.setdefault('type_coverage_limitation', []).append('基础难度可用题不足，在前置条件满足且已有至少两次有效证据时使用相邻D3题。')
        exposed_variants = {r[0] for r in conn.execute('''SELECT s.question_id
            FROM training_session_questions s JOIN training_sessions t ON t.id=s.session_id
            JOIN question_variants v ON v.question_id=s.question_id WHERE t.student_id=?
            ORDER BY s.selected_at DESC,s.rowid DESC LIMIT 30''',(student_id,))}
        remaining = [q for q in remaining if q.get('source_type') != 'generated_template'
                     or q['id'] not in recent | exposed_variants]
        state['recent_question_ids'] = [r['question_id'] for r in history]
        fresh = [q for q in remaining if not exposure_tokens(q)&recent_keys]
        if not fresh and conn.execute("SELECT 1 FROM question_knowledge_mappings WHERE taxonomy_version='function_v2' AND knowledge_point_id=? AND review_status='approved'",(state['target_knowledge_point_id'],)).fetchone():
            generated = create_runtime_question(conn,state)
            if generated:
                remaining.append(generated)
        if not remaining:
            _stop(state, 'coverage_limited', COVERAGE_MESSAGE)
            save_session(conn, state)
            return None
        # Exhaust all available fresh adjacent choices before reusing recent history.
        fresh = [q for q in remaining if not exposure_tokens(q)&recent_keys]
        unseen = [q for q in remaining if not exposure_tokens(q)&ever_keys]
        pool = unseen or fresh or remaining
        def rank(q):
            return ((0 if q['id'] not in recent else next((i for i,r in enumerate(reversed(history)) if r['question_id']==q['id']),30)), abs(q['difficulty'] - state['difficulty']), q['difficulty'], q['id'])
        preferred_type, ratios = select_question_type(pool,state['answers'],mastery['mastery_score'])
        # Record a desired type that is unavailable instead of silently skewing
        # the entire session toward the first surviving choice question.
        desired, _ = select_question_type([{'question_type':k} for k in ('single_choice','multiple_choice','fill_blank','subjective')], state['answers'], mastery['mastery_score'])
        if desired not in {q.get('question_type','single_choice') for q in pool} and desired in ('fill_blank','subjective'):
            nonchoices = [q for q in pool if q.get('question_type') in ('fill_blank','subjective')]
            if nonchoices:
                preferred_type, ratios = select_question_type(nonchoices,state['answers'],mastery['mastery_score'])
        if desired != preferred_type:
            note = f'{desired}在当前知识点、前置条件、难度与曝光范围内不足；回退到{preferred_type}。'
            limits = state.setdefault('type_coverage_limitation', [])
            if note not in limits: limits.append(note)
        type_pool = [q for q in pool if q.get('question_type','single_choice')==preferred_type]
        question = min(type_pool or pool, key=rank)
        state['question_type_ratios'] = ratios
        state['question_type_note'] = '题型按当前掌握度的目标比例与本轮数量缺口选择；缺题时回退可用题型。'
        note = '按当前建议难度选择新题。'
        if not fresh:
            note = '近期可用新题不足，使用此前做过但本轮未做过的题。'
        if question['difficulty'] != state['difficulty']:
            note += ('题目难度使用可用的相邻档位。' if abs(question['difficulty']-state['difficulty'])<=1
                     else '新题不足，已放宽难度范围；仍遵守掌握度与前置知识限制。')
        sequence = conn.execute('SELECT COALESCE(MAX(sequence_no),0)+1 FROM training_session_questions WHERE session_id=?', (session_id,)).fetchone()[0]
        conn.execute('''INSERT INTO training_session_questions(session_id,question_id,sequence_no,difficulty)
            VALUES (?,?,?,?)''', (session_id, question['id'], sequence, question['difficulty']))
        state.update(current_question=question, submitted=False, question_started_at=time.time(),
                     selection_note=note, question_hint_count=0, question_retry_count=0, hint_level=0, visible_hint=None, retry_pending=False)
        save_session(conn, state)
        return question


def _difficulty_cap(mastery):
    score, count = mastery['mastery_score'], mastery['attempt_count']
    if score is None or score < .4 or count <= 2:
        return 2
    if score < .6 or count < 4:
        return 3
    if score < .9 or count < 6:
        return 4
    return 5


def _update_decision(state, mastery, actual_difficulty):
    """Correct pairs and failure streaks, guarded by score, evidence and difficulty."""
    correct = state['answers'][-1]['is_correct']
    state['correct_streak'] = state['correct_streak'] + 1 if correct else 0
    state['wrong_streak'] = state['wrong_streak'] + 1 if not correct else 0
    previous = state['difficulty']
    recent = mastery['recent_accuracy'] or 0.
    cap = _difficulty_cap(mastery)
    if state['wrong_streak'] >= 2:
        state['difficulty'] = max(1, min(previous, actual_difficulty) - 1)
        state['decision_notes'].append('连续两题错误，降低建议难度。')
        # Keep three consecutive errors visible for the support stop condition.
    elif state['correct_streak'] >= 2 and recent >= .6:
        state['difficulty'] = min(cap, previous + 1, actual_difficulty + 1)
        state['correct_streak'] = 0
        state['decision_notes'].append('连续两题正确，结合掌握度、证据和实际题目难度适度提升。')
    state['difficulty'] = max(1, min(5, cap, state['difficulty']))
    state['difficulty_changes'].append(state['difficulty'])
    count = sum(not a.get('is_retry',False) for a in state['answers'])
    if count >= 8:
        _stop(state, 'completed', '已完成本轮8题，建议休息后继续。')
    elif count >= 5 and sum(a['is_correct'] for a in [a for a in state['answers'] if not a.get('is_retry',False) and a.get('is_correct') is not None][-3:]) >= 2 and mastery['mastery_score'] >= .8:
        _stop(state, 'completed', '已完成至少5题，近期表现及掌握度达到本轮目标。')
    elif state['wrong_streak'] >= 3 and mastery['mastery_score'] < .4:
        _stop(state, 'needs_support', '连续作答遇到困难，建议先巩固基础；仅在必要前置不足时回退。')


def submit_training_answer(student_id, session_id, question_id, user_answer, answer_time, *, database_path=None, answer_payload=None):
    """One transaction for answer, mastery read, difficulty update and session state."""
    if not isinstance(user_answer,str) or not math.isfinite(answer_time) or answer_time < 0:
        raise ValueError('请选择有效答案并提供有效作答时间。')
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = load_session(conn, session_id, student_id)
        previous = conn.execute('SELECT attempt_id FROM training_session_questions WHERE session_id=? AND question_id=?', (session_id, question_id)).fetchone()
        if previous and previous['attempt_id'] is not None and not state.get('retry_pending'):
            return state
        question = state['current_question']
        if state['status'] != 'active' or state['submitted'] or not question or question['id'] != question_id:
            raise ValueError('当前题目已变化，请刷新页面。')
        target = _target(student_id, state['target_knowledge_point_id'], database_path)
        if target['knowledge_point_id'] != state['target_knowledge_point_id']:
            _stop(state, 'prerequisite_blocked', target['reason'], target)
            save_session(conn, state)
            return state
        eligible = {q['id']: q for q in _eligible(state, database_path)}
        if question_id not in eligible:
            raise ValueError('当前题已退出可用范围，请点击下一题重新选择。')
        question = eligible[question_id]
        kind = question.get('question_type','single_choice')
        if kind!='subjective' and not user_answer.strip():
            raise ValueError('请填写答案后提交。')
        if kind=='subjective' and len(user_answer)>20000:
            raise ValueError('解题过程过长。')
        review_reason = None
        try:
            correct = evaluate_question(question,user_answer)
        except NeedsManualReview as error:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='answer_review_requests'").fetchone():
                raise
            correct = None
            review_reason = str(error)
        correct = int(correct) if correct is not None else None
        payload = {'text':user_answer}
        if kind=='subjective':
            image_data = (answer_payload or {}).get('image_bytes')
            if not user_answer.strip() and not image_data:
                raise ValueError('请填写解题过程或上传图片。')
            if image_data:
                payload['attachment_path'] = save_answer_image(image_data,database_path=database_path)
        scoring_status = 'pending' if correct is None else 'scored'
        cursor = conn.execute('''INSERT INTO attempts(student_id,question_id,user_answer,is_correct,
            answer_time,hint_count,retry_count) VALUES (?,?,?,?,?,?,?)''',
            (student_id, question_id, user_answer, correct, float(answer_time), state.get('question_hint_count',0), state.get('question_retry_count',0)))
        conn.execute('INSERT INTO attempt_details VALUES (?,?,?,?,?,?,?)',
                     (cursor.lastrowid,kind,json.dumps(payload,ensure_ascii=False),payload.get('attachment_path'),
                      scoring_status,correct,question.get('max_score') if kind=='subjective' else 1))
        submission_status = scoring_status
        if review_reason:
            submission_status = 'needs_manual_review'
            conn.execute('INSERT INTO answer_review_requests(attempt_id,status,reason) VALUES (?,?,?)',
                         (cursor.lastrowid,submission_status,review_reason))
        if kind=='subjective':
            submission_status='submitted_pending_review'
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='subjective_submissions'").fetchone():
                conn.execute('''INSERT INTO subjective_submissions(student_id,question_id,attempt_id,
                    text_answer,attachment_path,status,max_score) VALUES (?,?,?,?,?,?,?)''',
                    (student_id,question_id,cursor.lastrowid,user_answer,payload.get('attachment_path'),
                     submission_status,question['max_score']))
        is_retry = state.get('retry_pending',False)
        conn.execute('INSERT INTO training_attempt_links VALUES (?,?,?)',(cursor.lastrowid,session_id,question_id))
        conn.execute('UPDATE training_session_questions SET attempt_id=COALESCE(attempt_id,?) WHERE session_id=? AND question_id=?',
                     (cursor.lastrowid, session_id, question_id))
        state['answers'].append(dict(question_id=question_id, attempt_id=cursor.lastrowid, user_answer=user_answer,
                                     is_correct=correct, question_type=kind, scoring_status=scoring_status,
                                     submission_status=submission_status, review_reason=review_reason,
                                     answer_payload=payload, difficulty=question['difficulty'], error_type=None, is_retry=is_retry, answer_time=float(answer_time), hint_count=state.get('question_hint_count',0), retry_count=state.get('question_retry_count',0)))
        counts = Counter(a.get('question_type', 'single_choice') for a in state['answers'] if not a.get('is_retry'))
        state['question_type_counts'] = {k:counts[k] for k in ('single_choice','multiple_choice','fill_blank','subjective')}
        for k,v in state['question_type_counts'].items(): state[k+'_count'] = v
        mastery = calculate_knowledge_mastery(student_id, state['target_knowledge_point_id'],
                                             connection=conn, **_kwargs(database_path))
        state.update(submitted=True, final_mastery=mastery['mastery_score'], mastery=mastery,
                     current_question=question)
        if correct is None:
            if sum(not a.get('is_retry',False) for a in state['answers'])>=8:
                _stop(state,'completed','已完成本轮8题；待评阅作答仅保存，不计入掌握度。')
        elif not is_retry:
            _update_decision(state, mastery, question['difficulty'])
        else:
            state['status'] = state.get('retry_resume_status','active')
        state['retry_pending'] = False
        if state['status'] != 'active':
            logging.getLogger(__name__).info('Adaptive session mix: %s', state['question_type_counts'])
        save_session(conn, state)
    return state


def end_training_session(student_id, session_id, *, database_path=None):
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = load_session(conn, session_id, student_id)
        if state['status'] == 'active':
            mastery = calculate_knowledge_mastery(student_id, state['target_knowledge_point_id'], **_kwargs(database_path))
            state['final_mastery'] = mastery['mastery_score']
            _stop(state, 'user_ended', '你已主动结束本轮训练。')
            save_session(conn, state)
    return state


def get_training_session_summary(session_id, *, student_id=None, database_path=None):
    with closing(get_connection(database_path, read_only=True)) as conn:
        state = load_session(conn, session_id, student_id)
    first_answers = [a for a in state['answers'] if not a.get('is_retry',False)]
    total = len(first_answers)
    scored_answers = [a for a in first_answers if a['is_correct'] is not None]
    correct = sum(a['is_correct'] for a in scored_answers)
    from collections import Counter
    errors = Counter(a.get('error_type') for a in state['answers'] if a.get('error_type'))
    recommendation = generate_recommendation(state['student_id'], **_kwargs(database_path))
    return dict(session_id=session_id, status=state['status'], target_name=state['target_name'],
                target_knowledge_point_id=state['target_knowledge_point_id'], total=total, correct=correct,
                accuracy=correct / len(scored_answers) if scored_answers else None, scored_total=len(scored_answers),
                pending_total=total-len(scored_answers), initial_mastery=state['initial_mastery'],
                pending_subjective=sum(a['is_correct'] is None and a.get('question_type')=='subjective' for a in first_answers),
                pending_fill_blank=sum(a['is_correct'] is None and a.get('question_type')=='fill_blank' for a in first_answers),
                question_type_counts=dict(Counter(a.get('question_type','single_choice') for a in first_answers)),
                final_mastery=state['final_mastery'], actual_difficulties=[a['difficulty'] for a in state['answers']],
                suggested_difficulties=state['difficulty_changes'], stop_reason=state['stop_reason'],
                decision_notes=state['decision_notes'], recommendation=recommendation,
                prerequisite_suggestion=state['next_target'], hint_count=state.get('hint_count',0),
                retry_count=state.get('retry_count',0), error_types=dict(errors),
                main_error_types=[k for k,v in errors.items() if v==max(errors.values())] if errors else [])
