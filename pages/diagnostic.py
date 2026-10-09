"""Initial diagnostic UI; selection and persistence live in services."""
import sqlite3
import streamlit as st

from services.diagnostic import GROUPS, restore_diagnostic, start_diagnostic, submit_diagnostic_answer
from services.profile import format_percentage
from settings import get_active_taxonomy_version, get_database_path, get_topic_name
from services.math_text import math_markdown, render_math_text
from services.question_renderer import render_question, render_answer_input, read_answer_input, render_solution, TYPE_NAMES

st.title(get_topic_name() + '知识诊断测评')
st.write('测评包含选择题、填空题和解答题，用于从不同角度了解你的知识掌握情况。')
st.caption('预计题量：' + ('15题' if get_active_taxonomy_version() == 'geometry_v1' else '18题') + ' · 预计时间：约20–30分钟')
if get_active_taxonomy_version() == 'function_v1':
    st.info('首次诊断适用于函数新知识体系，请切换到 function_v2；旧版训练仍可使用。')
    st.stop()
student_id = st.session_state.get('student_id', 'S001')
try:
    state = restore_diagnostic(student_id)
    if state is None:
        if st.button('开始诊断'):
            state = start_diagnostic(student_id)
        else:
            st.stop()
    elif state['diagnostic_completed']:
        st.info('你已经完成过一次' + get_topic_name() + '诊断。')
        left, right = st.columns(2)
        if left.button('查看上次结果'):
            st.session_state.diagnostic_show_result = True
        if right.button('重新诊断'):
            state = start_diagnostic(student_id, restart=True)
    st.session_state.diagnostic_state = state
except (sqlite3.Error, ValueError, FileNotFoundError) as error:
    st.error(f'诊断读取失败：{error}')
    st.stop()

# Persisted state is authoritative; a fresh browser session resumes it too.
if not state['diagnostic_completed']:
    q = state['current_question']
    st.subheader(f"第 {state['question_index'] + 1} / {state['max_questions']} 题")
    st.progress(state['question_index'] / max(1, state['max_questions']))
    st.caption(TYPE_NAMES[q.get('question_type', 'single_choice')] + '题')
    if not render_question(st,q):
        from services.diagnostic import _upgrade_active
        _upgrade_active(state, None)
        st.rerun()
    widget_key = f"diagnostic_answer_{state['id']}_{q['id']}"
    render_answer_input(st,q,widget_key)
    answer,payload = read_answer_input(st,q,widget_key)
    if st.button('提交答案', key=f"diagnostic_submit_{state['id']}_{q['id']}"):
        if answer is None:
            st.warning('请选择一个答案后再提交。')
        else:
            try:
                state = submit_diagnostic_answer(state['id'], q['id'], answer, answer_payload=payload)
                st.session_state.diagnostic_state = state
                st.session_state.diagnostic_notice = (student_id, str(get_database_path()))
                st.session_state.diagnostic_pending_notice = state['answers'][-1].get('submission_status')
                st.rerun()
            except (sqlite3.Error, ValueError) as error:
                st.error(f'回答保存失败：{error}')
    if st.session_state.get('diagnostic_notice') == (student_id, str(get_database_path())):
        notice = st.session_state.get('diagnostic_pending_notice')
        if notice == 'submitted_pending_review':
            st.success('答案已提交，当前等待评阅；你可以继续诊断。')
        elif notice == 'needs_manual_review':
            st.info('答案已记录，暂需人工审核，不计入掌握度；你可以继续诊断。')
        else:
            st.success('回答已记录')
    if state['answers']:
        last = state['answers'][-1]
        with st.expander('查看上一题解析'):
            previous = next((p for p in state['pool'] if p['id'] == last['question_id']), None)
            if previous:
                render_solution(st, previous, submitted=True)
    st.stop()

st.success('诊断完成')
result = state['result']
columns = st.columns(3)
columns[0].metric('总作答题数', result['total'])
columns[1].metric('正确数', result['correct'])
scored_total = result.get('scored_total', result['total'])
columns[2].metric('自动评分正确率', format_percentage(result['correct'] / scored_total if scored_total else None))
st.write(f"自动评分部分：完成 {scored_total} 道，正确 {result['correct']} 道。")
st.write(f"解答题：已提交 {result.get('question_type_counts', {}).get('subjective', 0)} 道，待评阅 {result.get('pending_subjective', 0)} 道。")
if result.get('pending_fill_blank'):
    st.info(f"另有 {result['pending_fill_blank']} 道填空答案需要人工审核，暂不计入掌握度。")
st.subheader(('10' if get_active_taxonomy_version() == 'geometry_v1' else '15') + '知识点初始画像')
st.caption('这是自动评分部分生成的初步画像，包含已有历史证据；待主观题完成评分后，画像还可以进一步更新。')
groups = {'立体几何与空间向量': [f'G{i:03}' for i in range(1, 11)]} if get_active_taxonomy_version() == 'geometry_v1' else GROUPS
for group, keys in groups.items():
    st.subheader(group)
    rows = [dict(知识点=p['knowledge_point_name'], 掌握度=p.get('mastery_display') or format_percentage(p['mastery_score']),
                 掌握等级='待进一步训练' if p.get('evidence_status') == 'insufficient' else p['mastery_level'], 证据量=p['evidence_level'], 作答次数=p['attempt_count'])
            for p in result['profile'] if p['knowledge_point_id'] in keys]
    st.dataframe(rows, hide_index=True, use_container_width=True)
for label, items in result['explanations'].items():
    st.subheader(label)
    st.write('\n\n'.join(items) if items else '暂无')
if state['coverage_limitations']:
    with st.expander('本轮测评覆盖说明'):
        for note in state['coverage_limitations']:
            st.write(note)
rec = result['recommendation']
target = rec['target_knowledge']
st.subheader('下一步推荐')
st.write(f"推荐学习知识点：{target['knowledge_point_name']}")
st.write(target['reason'])
st.caption(f"建议难度：{target['difficulty_range'][0]}–{target['difficulty_range'][1]}")
for q in rec['recommended_questions']:
    render_math_text(q['stem'])
if not rec['recommended_questions']:
    st.info(rec.get('message', '暂无合适练习。'))
if st.button('开始针对性训练', disabled=not rec['recommended_questions']):
    from services.adaptive_training import start_training_session
    try:
        training = start_training_session(student_id, target_knowledge_point_id=target['knowledge_point_id'], lock_target=True)
        st.session_state.adaptive_session_id = training['id']
    except (sqlite3.Error, ValueError):
        st.error('训练暂时无法开始，请稍后重试。')
        st.stop()
    st.switch_page('pages/training.py')
