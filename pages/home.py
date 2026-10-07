"""Local learning-system landing page."""
import streamlit as st
from settings import get_active_taxonomy_version

st.title('高中数学个性化学习系统')
st.write('当前专题：函数')
st.write(f'当前知识体系：{get_active_taxonomy_version()}')
st.subheader('学习流程')
st.write('诊断 → 训练 → 掌握度更新 → 个性化推荐 → AI解释反馈')
st.write('首次使用时，先完成函数知识诊断，了解已有优势和需要巩固的基础。')
st.caption('首次测评包含选择题、填空题和解答题：18题，约20–30分钟。')
st.page_link('pages/diagnostic.py', label='开始首次诊断')
st.page_link('pages/training.py', label='开始训练')
