"""Display rule-based recommendations; this page does not collect answers."""

import sqlite3

import streamlit as st

from services.profile import format_percentage
from services.recommendation import generate_recommendation


st.title("个性化训练推荐")
st.write("当前学生：S001")
st.write("当前专题：函数")
try:
    recommendation = generate_recommendation("S001")
except (sqlite3.Error, ValueError, FileNotFoundError):
    st.error("推荐数据读取失败，请检查题库和前置知识关系，或稍后重试。")
    st.stop()

target = recommendation["target_knowledge"]
st.subheader(f"推荐学习内容：{target['knowledge_point_name']}（{target['knowledge_point_id']}）")
st.write(f"推荐类型：{target['recommendation_type']}")
st.write(f"推荐理由：{target['reason']}")
with st.expander('为什么推荐这里？'):
    st.write(target['reason'])
st.write(f"当前掌握度：{format_percentage(target['mastery_score'])}")
st.write(f"证据量：{target['evidence_level']}")
st.caption(f"优先难度：{target['difficulty_range'][0]}–{target['difficulty_range'][1]}；推荐由确定性规则生成。")
st.subheader("推荐练习")
if not recommendation["recommended_questions"]:
    st.info(recommendation.get('message',"当前知识点暂无可用练习题。"))
for index, question in enumerate(recommendation["recommended_questions"], 1):
    st.markdown(f"### 题 {index} · {question['id']}")
    st.text(question["stem"])
    st.caption(f"难度：{question['difficulty']}/5；知识点：{question['knowledge_point_name']}")
    if question["difficulty_fallback"]:
        st.caption("目标难度题目不足，本题为邻近难度补充。")
    if question["recently_practiced"]:
        st.caption("本题近期已练习，作为复习补充。")
