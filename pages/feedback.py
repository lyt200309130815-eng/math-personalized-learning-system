"""Explicit, single-click AI feedback with snapshot-bound session storage."""

import hashlib
import json
import os
import sqlite3

import streamlit as st

from services.feedback import (
    AIFeedbackUnavailable, build_feedback_context, build_rule_based_feedback, generate_learning_feedback,
)
from services.profile import format_percentage


st.title("AI 学习反馈")
st.write("当前学生：S001")
st.write("专题：函数")
st.caption("反馈仅解释已有结果，不参与掌握度计算或推荐决策。")
try:
    context = build_feedback_context("S001")
except (sqlite3.Error, ValueError, FileNotFoundError):
    st.error("学情数据读取失败，请稍后重试；首次使用请先初始化数据库。")
    st.stop()

target = context["recommendation"]["target_knowledge"]
st.subheader("确定性学情摘要")
st.write(f"推荐知识点：{target['knowledge_point_name']}（{target['knowledge_point_id']}）")
st.write(f"推荐类型：{target['recommendation_type']}")
st.write(f"当前掌握度：{format_percentage(target['mastery_score'])}")
st.write(f"证据量：{target['evidence_level']}")

fingerprint = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
if st.session_state.get("feedback_fingerprint") != fingerprint:
    st.session_state.feedback_fingerprint = fingerprint
    st.session_state.learning_feedback = None
    st.session_state.learning_feedback_source = None
    st.session_state.learning_feedback_error = None

has_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
if not has_key:
    st.info("尚未配置 AI 学习反馈服务。")
label = "重新生成" if st.session_state.learning_feedback else "生成 AI 学习反馈"
if st.button(label, disabled=not has_key):
    st.session_state.learning_feedback_error = None
    with st.spinner("正在生成学习反馈…"):
        try:
            st.session_state.learning_feedback = generate_learning_feedback("S001", context=context)
            st.session_state.learning_feedback_source = "AI 辅助反馈"
        except AIFeedbackUnavailable as error:
            st.session_state.learning_feedback_error = str(error)
            st.session_state.learning_feedback = build_rule_based_feedback(context)
            st.session_state.learning_feedback_source = "规则式学习反馈"

if st.button("查看规则式学习反馈"):
    st.session_state.learning_feedback = build_rule_based_feedback(context)
    st.session_state.learning_feedback_source = "规则式学习反馈"
    st.session_state.learning_feedback_error = None
if st.session_state.learning_feedback_error:
    st.warning(st.session_state.learning_feedback_error)
if st.session_state.learning_feedback:
    st.caption(st.session_state.learning_feedback_source)
    st.markdown(st.session_state.learning_feedback)
