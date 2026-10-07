"""Package reviewed legacy multi-type metadata without rewriting mathematical content."""
from copy import deepcopy
import re


def runtime_metadata(question):
    keys=('correct_answers','canonical_answer','sub_questions','rubric_source','reference_answers_by_subquestion','source_ranges')
    result={k:deepcopy(question[k]) for k in keys if k in question}
    kind=question.get('question_type','single_choice')
    if kind=='fill_blank':
        result.setdefault('canonical_answer',question.get('answer_expression') or question['accepted_answers'][0])
    if kind!='subjective' or 'sub_questions' in result:return result
    stem=question['stem']
    matches=list(re.finditer(r'(?:^|\n)\s*(?:例\s*\d+\s*)?[（(](\d+)[）)]\s*',stem))
    tasks=[(m[1],stem[m.end():matches[i+1].start() if i+1<len(matches) else len(stem)].strip()) for i,m in enumerate(matches)]
    if not tasks:tasks=[('1',stem)]
    rubric=deepcopy(question['rubric'])
    ids={number for number,_ in tasks}
    for row in rubric:
        match=re.search(r'第(\d+)问',row['criterion'])
        if match and match[1] in ids: row['sub_question']=match[1]
        elif len(tasks)==1:row['sub_question']=tasks[0][0]
        else:raise ValueError('已审核 rubric 无法可靠对应小问：'+question['id'])
    solution=question['reference_answer']
    numbered=list(re.finditer(r'(?:^|\n)\s*[（(](\d+)[）)]\s*',solution))
    answers={m[1]:solution[m.end():numbered[i+1].start() if i+1<len(numbered) else len(solution)].strip() for i,m in enumerate(numbered)}
    if len(tasks)==1:answers={tasks[0][0]:solution}
    if set(answers)!=ids:raise ValueError('已审核标准解答无法可靠对应小问：'+question['id'])
    subs=[{'id':n,'stem':text,'max_score':sum(r['score'] for r in rubric if r['sub_question']==n)} for n,text in tasks]
    if any(s['max_score']<=0 for s in subs):raise ValueError('小问缺少已审核评分点。')
    result.update(sub_questions=subs,rubric=rubric,rubric_source='derived_for_system',reference_answers_by_subquestion=answers)
    return result
