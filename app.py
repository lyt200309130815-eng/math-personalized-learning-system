"""Streamlit entry point for function-topic training."""

import streamlit as st
from settings import get_active_taxonomy_version, get_topic_name


st.set_page_config(page_title="高中数学个性化学习系统", page_icon="📚")
initial_version = get_active_taxonomy_version()


def update_topic():
    st.session_state.active_taxonomy_version = st.session_state.topic_selector


def update_student():
    st.session_state.student_id = st.session_state.student_selector


# Durable page context must not share keys with navigation-owned widgets.
# Widget cleanup can otherwise restore the default student/topic on a rerun.
st.session_state.setdefault('active_taxonomy_version', initial_version)
st.session_state.setdefault('student_id', 'S001')
topics = ['function_v2', 'geometry_v1']
if initial_version == 'function_v1':
    topics.insert(0, 'function_v1')
st.sidebar.selectbox('学习专题', topics, index=topics.index(initial_version),
                     format_func=lambda version: '函数（旧版）' if version == 'function_v1' else get_topic_name(version),
                     key='topic_selector', on_change=update_topic)
st.sidebar.text_input('当前学生编号', value=st.session_state.student_id,
                      key='student_selector', on_change=update_student)
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
with st.sidebar.expander('部署健康检查'):
    from services.health import get_health
    st.json(get_health())
page.run()
