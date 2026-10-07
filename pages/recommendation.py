"""Display rule-based recommendations; this page does not collect answers."""

import sqlite3

import streamlit as st

from services.profile import format_percentage
from services.recommendation import generate_recommendation
from services.adaptive_training import start_training_session
from settings import get_active_taxonomy_version
from services.math_text import render_math_text


st.title("个性化训练推荐")
student_id = st.session_state.get("student_id", "S001")
st.write(f"当前学生：{student_id}")
st.write("当前专题：函数")
try:
    recommendation = generate_recommendation(student_id)
except (sqlite3.Error, ValueError, FileNotFoundError):
    st.error("推荐数据读取失败，请检查题库和前置知识关系，或稍后重试。")
    st.stop()

target = recommendation["target_knowledge"]
st.subheader(f"推荐学习内容：{target['knowledge_point_name']}")
st.write(f"推荐类型：{target['recommendation_type']}")
render_math_text(f"推荐理由：{target['reason']}")
with st.expander('为什么推荐这里？'):
    st.write(target['reason'])
st.write(f"当前掌握度：{format_percentage(target['mastery_score'])}")
st.write(f"证据量：{target['evidence_level']}")
st.caption(f"建议难度：{target['difficulty_range'][0]}–{target['difficulty_range'][1]}；推荐由确定性规则生成。")
st.write('建议训练：5题，系统根据表现动态调整，最多8题；缺题时可能提前结束。')
if get_active_taxonomy_version() == 'function_v2':
    if st.button('开始推荐训练', type='primary', disabled=not recommendation['recommended_questions']):
        try:
            session = start_training_session(student_id, target_knowledge_point_id=target['knowledge_point_id'],
                                             taxonomy_version=get_active_taxonomy_version(), lock_target=True)
            st.session_state.adaptive_session_id = session['id']
        except (sqlite3.Error, ValueError) as error:
            st.warning(str(error))
        else:
            st.switch_page('pages/training.py')
else:
    if st.button('进入旧版训练'):
        st.switch_page('pages/training.py')
st.subheader('推荐题预览')
st.caption('进入训练后可正式作答。以下仅为难度预览，实际下一题由自适应训练逐题选择。')
if not recommendation["recommended_questions"]:
    st.info(recommendation.get('message',"当前知识点暂无可用练习题。"))
for index, question in enumerate(recommendation["recommended_questions"][:4], 1):
    st.write(f"题{index}：难度{question['difficulty']}")
    if question["difficulty_fallback"]:
        st.caption("目标难度题目不足，本题为邻近难度补充。")
    if question["recently_practiced"]:
        st.caption("本题近期已练习，作为复习补充。")
if recommendation['recommended_questions']:
    with st.expander('查看一道题干预览'):
        render_math_text(recommendation['recommended_questions'][0]['stem'])
        st.caption('进入训练后可正式作答。')
