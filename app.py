"""Streamlit entry point for function-topic training."""

import streamlit as st


st.set_page_config(page_title="高中数学智能训练系统", page_icon="📚")
# Preserve the answer widget's value when navigating away from its page.
if "selected_answer" in st.session_state:
    st.session_state.selected_answer = st.session_state.selected_answer
page = st.navigation([
    st.Page("pages/training.py", title="函数训练", default=True),
    st.Page("pages/profile.py", title="知识画像"),
    st.Page("pages/recommendation.py", title="个性化训练推荐"),
])
page.run()
