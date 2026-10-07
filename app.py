"""Streamlit entry point for function-topic training."""

import streamlit as st


st.set_page_config(page_title="高中数学个性化学习系统", page_icon="📚")
st.sidebar.text_input('当前学生编号', value='S001', key='student_id')
if not st.session_state.student_id.strip():
    st.warning('请输入学生编号。')
    st.stop()
# Preserve the answer widget's value when navigating away from its page.
if "selected_answer" in st.session_state:
    st.session_state.selected_answer = st.session_state.selected_answer
page = st.navigation([
    st.Page("pages/home.py", title="首页", default=True),
    st.Page("pages/diagnostic.py", title="首次诊断"),
    st.Page("pages/training.py", title="开始训练"),
    st.Page("pages/profile.py", title="学习画像"),
    st.Page("pages/recommendation.py", title="个性化推荐"),
    st.Page("pages/feedback.py", title="AI 学习反馈"),
])
page.run()
