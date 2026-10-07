"""V1.0D.1 conservative rescan; all results require human review."""
from copy import deepcopy
from pathlib import Path
import re

from services.answer_evaluator import evaluate_fill_blank, normalize_text
from services.question_validator import content_fingerprint, validate_candidate
from services.source_extractors.docx_question_extractor import read_docx_blocks, START, OPTION
from services.source_extractors.docx_multi_type_extractor import extract_multi_type_questions, _common, HEADER, TASK


def finalize(row):
    row['quality_status'] = 'reviewed'
    row['annotation_status'] = 'pending_review'
    row['fingerprint'] = content_fingerprint(row)
    checked = validate_candidate(row)
    row['validation_errors'] = checked['errors']
    row['validation_warnings'] = checked['warnings']
    if row['extraction_status'] == 'complete' and (checked['errors'] or checked['warnings']):
        if checked['errors']: row['extraction_status'] = 'incomplete'
        elif any('公式' in w or '表达式' in w for w in checked['warnings']): row['extraction_status'] = 'formula_warning'
        elif any('图' in w for w in checked['warnings']): row['extraction_status'] = 'image_required'
        else: row['extraction_status'] = 'manual_review'
    return row


def add_subquestions(row):
    """Keep common context; map source solutions to numbered tasks without guessing."""
    matches = list(TASK.finditer(row['stem']))
    tasks = [(m[1], row['stem'][m.start(2):matches[i+1].start() if i+1<len(matches) else len(row['stem'])].strip())
             for i,m in enumerate(matches)]
    if not tasks: tasks = [('1', row['stem'])]
    if len({n for n,_ in tasks}) != len(tasks):
        row['extraction_status'] = 'manual_review'
        return row
    solution = row['reference_answer']
    numbered = list(re.finditer(r'(?:^|\n)\s*[（(](\d+)[）)]', solution))
    by_number = {m[1]: solution[m.end():numbered[i+1].start() if i+1<len(numbered) else len(solution)].strip()
                 for i,m in enumerate(numbered)}
    if len(tasks)>1 and any(n not in by_number for n,_ in tasks):
        row['extraction_status']='manual_review'
        row['extraction_warnings'].append('多小问与标准解答边界不能可靠对应')
        return row
    if len(tasks)==1: by_number={tasks[0][0]:solution}
    subs=[];rubric=[]
    for number, task in tasks:
        source_score = re.search(r'[（(](\d+)分[）)]', task)
        # These are system review drafts even when the source supplies a total.
        score = int(source_score[1]) if source_score else 6
        subs.append({'id':number,'stem':task,'max_score':score})
        steps = [s.strip() for s in re.split(r'\n', by_number[number]) if s.strip()]
        chosen = steps if len(steps)>1 else [by_number[number]]
        # Derive criteria from literal source solution segments, never invent answers.
        weights = [score/len(chosen)] * len(chosen)
        for step,weight in zip(chosen,weights):
            rubric.append({'sub_question':number,'criterion':'完成原解答步骤：'+step,'score':weight})
    row.update(sub_questions=subs,reference_answers_by_subquestion=by_number,rubric=rubric,
               max_score=sum(s['max_score'] for s in subs),rubric_source='derived_for_system',
               rubric_basis='依据原标准解答逐段拆分；分步分值为系统草案，非原资料官方评分细则。')
    return row


def extract_expansion_questions(path):
    path=Path(path)
    rows=[]
    for old in extract_multi_type_questions(path):
        row=deepcopy(old)
        row['previous_candidate_id']=old['id']
        if row['question_type']=='fill_blank':
            expected=row['answer_expression']
            row['canonical_answer']=expected
            if expected.startswith('{') and expected.endswith('}'):
                try:
                    evaluate_fill_blank(expected,expected,'set')
                    row['answer_type']='set'
                except ValueError:
                    row['extraction_status']='manual_review'
            # Unparsed mathematical notation must not masquerade as text matching.
            if row['answer_type']=='text' and re.search(r'[0-9=<>≤≥{}^]|sqrt|log',expected):
                row['extraction_status']='manual_review'
                row['extraction_warnings'].append('数学标准答案不受当前安全解析器支持')
        else:
            add_subquestions(row)
        rows.append(finalize(row))
    blocks=read_docx_blocks(path)
    section=''
    for index,block in enumerate(blocks):
        if re.search(r'^[一二三四五]、',block['text']): section=block['text']
        if not re.match(r'^答案\s*[:：]?',block['text']): continue
        starts=[i for i in range(index) if START.match(blocks[i]['text'])]
        if not starts: continue
        start=starts[-1]
        joined='\n'.join(b['text'] for b in blocks[start:index])
        raw=re.sub(r'^答案\s*[:：]?\s*','',block['text']).strip()
        explicit='多选' in joined or '多项选择' in section
        if not explicit: continue
        matches=list(OPTION.finditer(joined))
        if not matches and not re.fullmatch(r'[ABCD]{2,4}',raw): continue
        end=index+1
        while end<len(blocks) and not START.match(blocks[end]['text']) and not HEADER.search(blocks[end]['text']) and not re.match(r'^答案',blocks[end]['text']): end+=1
        explanation=re.sub(r'^解析\s*[:：]?\s*','','\n'.join(b['text'] for b in blocks[index+1:end])).strip()
        stem=joined[:matches[0].start()].strip() if matches else joined
        row=_common(path,blocks,start,end,stem,explanation,'multiple_choice')
        row['id']='FM-'+row['id'][3:]
        options={}
        for i,m in enumerate(matches):
            value=joined[m.end():matches[i+1].start() if i+1<len(matches) else len(joined)].strip()
            if m[1] in options: value='[选项边界待核]'+value
            options[m[1]]=value
        row.update(options=options,correct_answers=list(raw) if re.fullmatch(r'[ABCD]{2,4}',raw) else [],raw_answer=raw)
        if not explanation or set(options)!=set('ABCD') or not row['correct_answers']:
            row['extraction_status']='incomplete'
        if re.search(r'如图|下图|图中|图示|图所示|图象如',stem+'\n'+explanation):
            row['extraction_status']='image_required'
        rows.append(finalize(row))
    return rows
