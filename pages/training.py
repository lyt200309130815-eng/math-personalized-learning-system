"""Chinese training interface with single-submission learning data collection."""

import sqlite3

import streamlit as st

from database.database import get_training_questions
from services.training import advance_question, initialize_training_state, submit_training_answer
from settings import get_active_taxonomy_version, get_database_path


def submit_answer(question_id: str, correct_answer: str) -> None:
    """Delegate persistence; leave the question available if the write fails."""
    try:
        submit_training_answer(st.session_state, question_id, correct_answer)
    except (sqlite3.Error, ValueError):
        st.session_state.feedback = "答题记录保存失败，请再次点击提交答案。"


def next_question(question_count: int) -> None:
    """Advance cyclically and clear the previous question's widget and feedback."""
    advance_question(st.session_state, question_count)


st.title("高中数学智能训练系统")
st.write("当前专题：函数")
try:
    questions = get_training_questions()
except (FileNotFoundError, sqlite3.Error, ValueError):
    st.error("题库读取失败，请检查数据库和题目数据；首次使用请先运行 python init_db.py。")
    st.stop()

if not questions:
    st.info("暂无函数专题选择题，请先初始化题库。")
    st.stop()

context = (get_active_taxonomy_version(), str(get_database_path()))
if st.session_state.get('training_context') != context:
    for key in ('question_index','selected_answer','submitted','feedback','recorded_attempt_id','answer_time','question_started_at'):
        st.session_state.pop(key,None)
    st.session_state.training_context = context
initialize_training_state(st.session_state)

question = questions[st.session_state.question_index % len(questions)]
st.subheader(f"第 {st.session_state.question_index % len(questions) + 1} / {len(questions)} 题（{question['id']}）")
st.text(question["stem"])
st.caption(f"知识点：{question['knowledge_point_name']}（{question['knowledge_point_id']}） · 难度：{question['difficulty']}/5")
st.radio("请选择答案", ["A", "B", "C", "D"], index=None,
         format_func=lambda choice: f"{choice}. {question['options'][choice]}",
         key="selected_answer", disabled=st.session_state.submitted)
st.button("提交答案", on_click=submit_answer, args=(question["id"], question["answer"]),
          disabled=st.session_state.submitted)

if st.session_state.submitted:
    if st.session_state.feedback == "回答正确":
        st.success(st.session_state.feedback)
    else:
        st.error(st.session_state.feedback)
    st.text(f"正确答案：{question['answer']}. {question['options'][question['answer']]}")
    st.write(f"知识点：{question['knowledge_point_name']}；难度：{question['difficulty']}/5")
    if question.get("explanation"):
        with st.expander("查看解析"):
            st.text(question["explanation"])
    st.caption("本次答题已记录")
elif st.session_state.feedback:
    st.warning(st.session_state.feedback)

st.button("下一题", on_click=next_question, args=(len(questions),))
st.caption("最后一题后将回到第一题。")
