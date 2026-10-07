"""Read-only student knowledge profile using fresh mastery service results."""

import sqlite3

import streamlit as st

from services.mastery import calculate_student_mastery
from services.profile import build_profile_data
from settings import get_active_taxonomy_version


st.title("高中数学智能训练系统")
st.header("知识画像")
if get_active_taxonomy_version()=='function_v2':
    st.subheader('函数学习画像')
student_id = st.session_state.get("student_id", "S001")
st.write(f"当前学生：{student_id}")
st.write("当前专题：函数")
st.caption("知识画像根据历史训练数据动态计算，仅作为学习诊断参考。")

try:
    from database.training_review import pending_counts
    profile = build_profile_data(calculate_student_mastery(student_id),pending_by_point=pending_counts(student_id,taxonomy_version=get_active_taxonomy_version()))
except (sqlite3.Error, ValueError, FileNotFoundError):
    st.error("知识画像读取失败，请稍后重试；首次使用请先运行 python init_db.py。")
    st.stop()

overview = profile["overview"]
st.subheader("总体概览")
columns = st.columns(4)
columns[0].metric("已训练知识点", f"{overview['trained_count']} / {overview['knowledge_point_count']}")
columns[1].metric("未评估知识点", str(overview["unevaluated_count"]))
columns[2].metric("有效评分证据", f"{overview['total_attempts']} 次")
columns[3].metric("总体正确率", overview["overall_accuracy_display"])
st.caption(f"待评阅作答：{overview['pending_total']}次，暂不计入掌握度。")
if overview["total_attempts"] == 0:
    st.info("暂无训练数据")

st.subheader("知识点掌握情况")
if profile["chart"]:
    st.vega_lite_chart(spec=profile["chart_spec"], use_container_width=True)
if profile["unevaluated"]:
    st.write("以下知识点尚未评估：" + "、".join(profile["unevaluated"]))
    st.caption("未训练不等于掌握度为 0；未评估知识点不绘制为零分。")

st.subheader("知识点画像")
group_names = {'K001':'基础概念','K002':'基础概念',
               **{f'K{i:03d}':'函数性质' for i in range(3,7)},
               **{f'K{i:03d}':'基本初等函数' for i in range(7,12)},
               **{f'K{i:03d}':'函数综合应用' for i in range(12,16)}}
previous_group = None
for point in profile["points"]:
    if get_active_taxonomy_version()=='function_v2':
        group = group_names[point['knowledge_point_id']]
        if group!=previous_group: st.subheader(group)
        previous_group=group
    st.markdown(f"### {point['knowledge_point_id']} {point['knowledge_point_name']}")
    st.write(f"掌握度：{point['mastery_display']}；掌握等级：{point['mastery_level']}")
    st.write(f"训练次数：{point['attempt_count']}；正确次数：{point['correct_count']}；证据量：{point['evidence_level']}")
    st.write(f"有效评分证据：{point['attempt_count']}次；待评阅大题：{point['pending_subjective_count']}次；待人工审核填空：{point['pending_fill_blank_count']}次")
    if point["evidence_note"]:
        st.info(point["evidence_note"])
    with st.expander(f"查看 {point['knowledge_point_name']} 的详细指标"):
        for label, field in (("总体正确率 A", "overall_accuracy"), ("近期正确率 R", "recent_accuracy"),
                             ("稳定性 S", "stability"), ("难度表现 D", "difficulty_performance"),
                             ("最终掌握度 M", "mastery_score")):
            st.write(f"{label}：{point['metric_displays'][field]}")
        st.write(f"训练次数：{point['attempt_count']}；正确次数：{point['correct_count']}")
        st.write(f"证据量：{point['evidence_level']}")
