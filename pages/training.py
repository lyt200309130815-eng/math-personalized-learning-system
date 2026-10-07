"""Adaptive V2 training UI with the preserved V1 fallback."""
from pathlib import Path
import runpy
import sqlite3
import time

import streamlit as st

from database.database import get_knowledge_points
from database.training_sessions import get_latest_session
from database.multi_type import migrate_multi_type
from services.question_renderer import render_answer_input, read_answer_input, render_question, render_feedback, TYPE_NAMES
from services.adaptive_training import (
    start_training_session, get_next_question, submit_training_answer,
    get_training_session, get_training_session_summary, end_training_session, difficulty_band,
)
from services.training_support import request_hint, retry_question, select_error_type
from services.error_diagnosis import ERROR_LABELS, suggest_error
from services.profile import format_percentage
from services.recommendation import generate_recommendation
from settings import get_active_taxonomy_version, get_database_path
from services.math_text import math_markdown, render_math_text

if get_active_taxonomy_version() == 'function_v1':
    runpy.run_path(str(Path(__file__).with_name('_training_v1.py')))
    st.stop()

student_id = st.session_state.get('student_id', 'S001')
context = (student_id, str(get_database_path()))
if st.session_state.get('adaptive_context') != context:
    st.session_state.adaptive_context = context
    st.session_state.adaptive_error = None
st.title('自适应函数训练')
st.caption('每轮围绕一个主要知识点混合练习不同题型；确定性判分后更新掌握度，待评阅作答只保存。通常5–8题。')


def submit_current(session_id, question_id, widget_key):
    current = get_training_session(student_id,session_id)
    answer,payload = read_answer_input(st,current['current_question'],widget_key)
    if answer is None:
        st.session_state.adaptive_error = '请选择一个答案后再提交。'
        return
    try:
        current = get_training_session(student_id, session_id)
        submit_training_answer(student_id, session_id, question_id, answer,
                               max(0., time.time() - current['question_started_at']), answer_payload=payload)
        st.session_state.adaptive_error = None
    except ValueError as error:
        st.session_state.adaptive_error = str(error)
    except (sqlite3.Error,OSError):
        st.session_state.adaptive_error = '回答未保存，请重新选择题目或重试。'


def next_question(session_id):
    try:
        get_next_question(student_id, session_id)
        st.session_state.adaptive_error = None
    except (sqlite3.Error, ValueError):
        st.session_state.adaptive_error = '下一题暂时无法读取，请稍后重试。'


try:
    migrate_multi_type()
    state = get_latest_session(student_id)
    if state is None or state['status'] != 'active':
        rec = generate_recommendation(student_id)
        st.write('当前优先：' + rec['target_knowledge']['knowledge_point_name'])
        st.caption(rec['target_knowledge']['reason'])
        if st.button('开始个性化训练'):
            state = start_training_session(student_id)
            st.session_state.adaptive_error = None
        with st.expander('选择知识点训练'):
            points = get_knowledge_points()
            by_id = {p['id']: p['name'] for p in points}
            chosen = st.selectbox('学习知识点', list(by_id), format_func=lambda key: by_id[key])
            if st.button('开始所选知识点训练'):
                state = start_training_session(student_id, target_knowledge_point_id=chosen)
                st.session_state.adaptive_error = None
        if state is None:
            st.stop()
    if state['status'] == 'active' and (state['current_question'] is None or not state['submitted']):
        get_next_question(student_id, state['id'])
        state = get_training_session(student_id, state['id'])
    st.session_state.adaptive_session_id = state['id']
    st.session_state.adaptive_training_state = state
    if st.session_state.get('adaptive_error'):
        st.warning(st.session_state.adaptive_error)
    if state['submitted']:
        render_feedback(st,state['answers'][-1])
        q = state['current_question']
        if state['answers'][-1]['is_correct'] == 0:
            suggestion, reason = suggest_error(state.get('hint_level',0), state['answers'][-1].get('answer_time',0))
            st.caption('错因建议：' + ERROR_LABELS[suggestion] + '。' + reason)
            chosen_error = st.selectbox('你觉得自己主要卡在哪里？', list(ERROR_LABELS), index=None,
                format_func=lambda code: ERROR_LABELS[code], key=f"error_{state['answers'][-1]['attempt_id']}")
            if st.button('保存错因', disabled=chosen_error is None):
                select_error_type(student_id,state['id'],chosen_error)
                st.rerun()
            if st.button('再试一次'):
                retry_question(student_id,state['id'])
                st.rerun()
        st.caption('当前掌握度：' + format_percentage(state['final_mastery']))
    if state['current_question'] and state['status'] in ('active','completed','needs_support'):
        for level,label in enumerate(['提示1','提示2','提示3','查看完整解析'],1):
            if st.button(label):
                request_hint(student_id,state['id'],level)
                st.rerun()
        if state.get('visible_hint'):
            render_math_text(state['visible_hint'])
    question_count = sum(not a.get('is_retry',False) for a in state['answers'])
    if state['status'] == 'active':
        st.subheader('当前训练目标：' + state['target_name'])
        low, high = difficulty_band(state['difficulty'])
        st.write(f'当前建议难度：{low}–{high}')
        st.write(f"进度：{question_count} / 8")
        number = question_count if state['submitted'] else question_count + 1
        st.write(f'第 {max(1, number)} / 8 题')
        st.progress(question_count / 8)
        st.caption(state['target_reason'])
        q = state['current_question']
        render_question(st,q)
        st.caption(f"本题难度：{q['difficulty']}；{state['selection_note']}")
        key = f"adaptive_answer_{state['id']}_{q['id']}_{state.get('question_retry_count',0)}"
        render_answer_input(st,q,key,disabled=state['submitted'])
        st.caption(TYPE_NAMES[q.get('question_type','single_choice')] + '题')
        st.button('提交答案', on_click=submit_current, args=(state['id'], q['id'], key), disabled=state['submitted'])
        st.button('下一题', on_click=next_question, args=(state['id'],), disabled=not state['submitted'])
        if st.session_state.get('adaptive_error'):
            st.button('重新选择题目', on_click=next_question, args=(state['id'],))
        if st.button('结束本轮训练'):
            end_training_session(student_id, state['id'])
            st.rerun()
    else:
        summary = get_training_session_summary(state['id'], student_id=student_id)
        st.subheader('本轮训练结束')
        with st.expander('查看本次训练结果', expanded=True):
            st.write('本次训练知识点：' + summary['target_name'])
            columns = st.columns(3)
            columns[0].metric('完成题数', summary['total'])
            columns[1].metric('正确数', summary['correct'])
            columns[2].metric('正确率', format_percentage(summary['accuracy']))
            st.write('本次题型分布：'+'、'.join(f"{TYPE_NAMES[k]} {v}题" for k,v in summary['question_type_counts'].items()))
            st.write(f"自动/已评分证据：{summary['scored_total']}；待评阅大题：{summary['pending_subjective']}；待人工审核填空：{summary['pending_fill_blank']}（正确率仅统计已评分题）")
            st.write('训练前掌握度：' + format_percentage(summary['initial_mastery']))
            st.write('训练后掌握度：' + format_percentage(summary['final_mastery']))
            st.write('实际题目难度：' + (' → '.join(map(str, summary['actual_difficulties'])) or '尚未作答'))
            st.write('建议难度变化：' + (' → '.join(map(str, summary['suggested_difficulties'])) or '尚未作答'))
            st.write(f"本次使用提示次数：{summary['hint_count']}")
            st.write(f"重试次数：{summary['retry_count']}")
            st.write('主要错误类型：' + ('、'.join(ERROR_LABELS[k] for k in summary['main_error_types']) or '尚未选择错因'))
            st.info(summary['stop_reason'])
            for note in dict.fromkeys(summary['decision_notes']):
                st.caption(note)
        target = summary['recommendation']['target_knowledge']
        st.subheader('下一步建议：' + target['knowledge_point_name'])
        st.write(target['reason'])
        if summary['prerequisite_suggestion']:
            st.write(summary['prerequisite_suggestion']['reason'])
        st.page_link('pages/profile.py', label='查看学习画像')
        st.page_link('pages/recommendation.py', label='继续个性化推荐')
        st.page_link('pages/feedback.py', label='查看AI学习反馈')
except (sqlite3.Error, ValueError, FileNotFoundError):
    st.error('训练暂时不可用，请检查函数知识体系是否已迁移，或稍后重试。')
