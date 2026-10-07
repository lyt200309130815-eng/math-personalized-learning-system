"""One question/input abstraction for the training page's three question types."""
from services.math_text import math_markdown, render_math_text

SUBJECTIVE_NOTICE = '主观题自动识别与评分功能将在后续版本完善。'
TYPE_NAMES = {'single_choice':'单选','multiple_choice':'多选','fill_blank':'填空','subjective':'大题'}


def render_question(st, question):
    render_math_text(question['stem'])
    if question.get('question_type')=='subjective':
        for sub in question.get('sub_questions',[]):
            # Preserve common conditions in the stem; no solution is displayed.
            st.caption(f"第{sub['id']}问 · {sub['max_score']:g}分")
            render_math_text(sub['stem'])
        st.write(f"总分：{question.get('max_score',0):g}分（本阶段不自动评分）")


def render_feedback(st, answer):
    if answer.get('submission_status')=='needs_manual_review':
        st.warning('答案已保存，需人工审核（needs_manual_review）；暂不计入掌握度。')
    elif answer.get('is_correct') is None:
        render_saved_answer(st,answer)
        st.success('答案已提交，当前等待评阅。解题过程已保存，待评阅；当前不计入掌握度。')
    elif answer['is_correct']:
        st.success('回答正确')
    else:
        st.error('回答错误')


def render_answer_input(st,question,key,*,disabled=False):
    kind = question.get('question_type','single_choice')
    if kind=='single_choice':
        for choice,text in question['options'].items():
            render_math_text(f'{choice}. {text}')
        # Widget labels have a restricted Markdown parser. Mathematical option
        # content belongs to the shared renderer, never to format_func.
        st.radio('请选择答案',list(question['options']),index=None,key=key,disabled=disabled,horizontal=True)
    elif kind=='fill_blank':
        st.text_input('请输入填空答案',key=key,disabled=disabled,max_chars=500)
        st.caption('支持分数、普通数学表达式与区间，例如 1/2、(x-1)*(x+1)、[0,1)。')
    elif kind=='multiple_choice':
        st.write('请选择所有正确选项')
        for choice, text in question['options'].items():
            render_math_text(f'{choice}. {text}')
            st.checkbox(f'{choice}. 选择此项', key=key+'_'+choice, disabled=disabled)
        st.caption('全部选对才得分，选项顺序不影响判分。')
    elif kind=='subjective':
        st.text_area('请输入解题过程',key=key,disabled=disabled,max_chars=20000)
        upload = st.file_uploader('上传解题图片',type=['png','jpg','jpeg','webp'],
                                  key=key+'_image',disabled=disabled)
        if upload is not None: st.image(upload,caption='解题图片预览')
        st.info(SUBJECTIVE_NOTICE)
    else:
        raise ValueError('不支持的题型。')


def read_answer_input(st,question,key):
    text = st.session_state.get(key)
    if question.get('question_type') == 'multiple_choice':
        import json
        return json.dumps([c for c in question['options'] if st.session_state.get(key+'_'+c, False)]), None
    if question.get('question_type','single_choice')!='subjective': return text,None
    upload = st.session_state.get(key+'_image')
    payload = {'text':text or ''}
    if upload is not None:
        payload['image_bytes'] = upload.getvalue()
    return text or '',payload


def render_saved_answer(st,answer):
    if answer.get('question_type')!='subjective': return
    payload = answer.get('answer_payload',{})
    if payload.get('text'): st.write('已保存解题过程：'+payload['text'])
    if payload.get('attachment_path'): st.image(payload['attachment_path'],caption='已保存的解题图片')
    st.info(SUBJECTIVE_NOTICE)
