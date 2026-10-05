"""Streamlit entry point for function-topic training."""

import streamlit as st


st.set_page_config(page_title="高中数学智能训练系统", page_icon="📚")
page = st.navigation([st.Page("pages/training.py", title="函数训练", default=True)],
                     position="hidden")
page.run()
