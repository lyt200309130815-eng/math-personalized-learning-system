"""Chinese training interface; answers remain in session memory only."""

import sqlite3

import streamlit as st

from database.database import get_training_questions


def submit_answer(correct_answer: str) -> None:
    """Update feedback before the page reruns; never write student records."""
    selected = st.session_state.selected_answer
    if selected is None:
        st.session_state.feedback = "请选择一个答案后再提交。"
        return
    st.session_state.submitted = True
    st.session_state.feedback = "回答正确" if selected == correct_answer else "回答错误"


def next_question(question_count: int) -> None:
    """Advance cyclically and clear the previous question's widget and feedback."""
    st.session_state.question_index = (st.session_state.question_index + 1) % question_count
    st.session_state.selected_answer = None
    st.session_state.submitted = False
    st.session_state.feedback = None


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

for key, default in {"question_index": 0, "selected_answer": None,
                     "submitted": False, "feedback": None}.items():
    if key not in st.session_state:
        st.session_state[key] = default

question = questions[st.session_state.question_index % len(questions)]
st.subheader(f"第 {st.session_state.question_index % len(questions) + 1} / {len(questions)} 题（{question['id']}）")
st.text(question["stem"])
st.caption(f"知识点：{question['knowledge_point_name']}（{question['knowledge_point_id']}） · 难度：{question['difficulty']}/5")
st.radio("请选择答案", ["A", "B", "C", "D"], index=None,
         format_func=lambda choice: f"{choice}. {question['options'][choice]}",
         key="selected_answer", disabled=st.session_state.submitted)
st.button("提交答案", on_click=submit_answer, args=(question["answer"],),
          disabled=st.session_state.submitted)

if st.session_state.submitted:
    if st.session_state.feedback == "回答正确":
        st.success(st.session_state.feedback)
    else:
        st.error(st.session_state.feedback)
    st.text(f"正确答案：{question['answer']}. {question['options'][question['answer']]}")
    st.write(f"知识点：{question['knowledge_point_name']}；难度：{question['difficulty']}/5")
elif st.session_state.feedback:
    st.warning(st.session_state.feedback)

st.button("下一题", on_click=next_question, args=(len(questions),))
st.caption("最后一题后将回到第一题。")
