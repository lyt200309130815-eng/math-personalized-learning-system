"""Read-only extraction of explicit blanks and worked solutions, never choices."""
import hashlib
from pathlib import Path
import re

from services.answer_evaluator import evaluate_fill_blank, normalize_text
from services.question_validator import content_fingerprint, validate_candidate
from services.source_extractors.docx_question_extractor import read_docx_blocks, START, OPTION, _annotation

MAJOR_START = re.compile(r'^(?:例|跟踪训练)\s*\d+|^\d+[.．、](?!\d)')
HEADER = re.compile(r'^题型|^课时|^思维升华|^感悟|^防范|^方法|^命题|^考试要求|^重点解读|^[一二三四五]、|\[每小题|\[分值|成套的课件|QQ群|百度网盘群')
SOLUTION = re.compile(r'^(?:解|证明|解析)(?:\s|[:：])')
TASK = re.compile(r'^(?:(?:例|跟踪训练)\s*\d+\s*)?[（(](\d+)[）)]\s*(.+)',re.MULTILINE)


def _common(path,blocks,start,end,stem,explanation,kind):
    used = blocks[start:end]
    images = list(dict.fromkeys(v for b in used for v in b['images']))
    warnings = list(dict.fromkeys(v for b in used for v in b['warnings']))
    if re.search(r'如图|下图|图中|图示|图所示|图象如',stem+'\n'+explanation):
        warnings.append('解答依赖图象，优先留待图片人工审核')
    locator = f"word/document.xml paragraphs {blocks[start]['index']}–{blocks[end-1]['index']}"
    primary,related,prerequisites,difficulty,abilities,methods = _annotation(stem,explanation,path.stem)
    prefix = 'FF-' if kind=='fill_blank' else 'FS-'
    row = dict(id=prefix+hashlib.sha256((path.as_posix()+locator).encode()).hexdigest()[:16],
               question_type=kind,stem=stem,explanation=explanation,taxonomy_version='function_v2',
               primary_knowledge_point_id=primary,related_knowledge_point_ids=related,
               question_prerequisite_ids=prerequisites,difficulty=difficulty,ability_tags=abilities,
               method_tags=methods,estimated_time=difficulty*(60 if kind=='fill_blank' else 180),
               source_type='docx',source_file=path.as_posix(),source_section=path.stem,
               source_question_number=START.match(stem).group(0).strip() if START.match(stem) else None,
               source_locator=locator,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               source_url=None,license=None,usage_note='本地提供的 DOCX 提取；来源许可待人工核实，不自动批准或发布。',
               extraction_status='image_required' if images else 'formula_warning' if warnings else 'complete',
               quality_status='reviewed',review_notes=['知识点、难度、答案格式为规则草标，需人工审核；尚未批准。'],
               version=1,extraction_warnings=warnings,image_resources=images,annotation_status='pending_review')
    return row


def _finish(row):
    row['fingerprint'] = content_fingerprint(row)
    checked = validate_candidate(row)
    row['review_notes'].extend(checked['errors']+checked['warnings'])
    row['validation_errors'] = checked['errors']
    row['validation_warnings'] = checked['warnings']
    return row


def extract_multi_type_questions(path):
    """Scan every paragraph, accepting only explicit blank/solution boundaries."""
    path = Path(path)
    blocks = read_docx_blocks(path)
    results = []
    for index,block in enumerate(blocks):
        if re.match(r'^答案\s*[:：]?',block['text']):
            # An answer block closes a fill question. Numbered subitems are
            # boundaries here; unlike subjective solutions, they are standalone.
            starts = [i for i in range(index) if START.match(blocks[i]['text'])]
            if not starts: continue
            start = starts[-1]
            stem = '\n'.join(b['text'] for b in blocks[start:index]).strip()
            raw = re.sub(r'^答案\s*[:：]?\s*','',block['text']).strip()
            if OPTION.search(stem) or re.fullmatch(r'[ABCD]{1,4}',raw) or not re.search(r'\u3000{2,}|_{3,}',stem):
                continue
            end = index+1
            while end<len(blocks) and not START.match(blocks[end]['text']) and not HEADER.search(blocks[end]['text']) and not re.match(r'^答案',blocks[end]['text']):
                end+=1
            explanation = '\n'.join(b['text'] for b in blocks[index+1:end]).strip()
            explanation = re.sub(r'^解析\s*[:：]?\s*','',explanation)
            row = _common(path,blocks,start,end,stem,explanation,'fill_blank')
            expected = normalize_text(raw)
            expected = re.sub(r'(?<=\d)\s+(?=\d)','',expected)
            answer_type = 'text'
            for kind in ('numeric','interval','expression'):
                try:
                    if evaluate_fill_blank(expected,expected,kind):
                        answer_type=kind
                        break
                except ValueError:
                    continue
            row.update(answer_expression=expected,accepted_answers=[expected],answer_type=answer_type,raw_answer=raw)
            if len(re.findall(r'\u3000{2,}|_{3,}',stem))>1:
                row['extraction_warnings'].append('多空题尚未建立逐空答案映射，不进入首批')
                row['extraction_status']='manual_review'
            if re.search(r'答案不唯一|答案不惟一|例如|如：',raw):
                row['extraction_warnings'].append('开放性填空答案不唯一，不适合首批确定性自动判分')
                row['extraction_status']='manual_review'
            results.append(_finish(row))
        elif SOLUTION.match(block['text']):
            starts = [i for i in range(index) if MAJOR_START.match(blocks[i]['text'])]
            if not starts: continue
            start = starts[-1]
            if any(re.match(r'^答案',b['text']) or SOLUTION.match(b['text']) for b in blocks[start:index]):
                continue
            stem_blocks = blocks[start:index]
            stem = '\n'.join(b['text'] for b in stem_blocks).strip()
            if OPTION.search(stem) or not re.search(r'求|证明|判断|讨论|确定|写出|选择|比较',stem): continue
            task_numbers={match[1] for match in TASK.finditer(stem)}
            end = index+1
            while end<len(blocks) and not MAJOR_START.match(blocks[end]['text']) and not HEADER.search(blocks[end]['text']):
                next_task=TASK.match(blocks[end]['text'])
                if task_numbers and next_task and next_task[1] not in task_numbers:
                    break
                end+=1
            explanation_blocks = blocks[index:end]
            explanation = '\n'.join(b['text'] for b in explanation_blocks).strip()
            explanation = re.sub(r'^(?:解|证明|解析)\s*[:：]?\s*','',explanation)
            row = _common(path,blocks,start,end,stem,explanation,'subjective')
            criteria = []
            for text in (b['text'] for b in stem_blocks):
                for match in re.finditer(r'^(?:(?:例|跟踪训练)\s*\d+\s*)?[（(](\d+)[）)]\s*(.+?)[（(](\d+)分[）)]',text):
                    criteria.append({'criterion':f"第{match[1]}问：{match[2].strip('；;。.')}",'score':int(match[3])})
            if not criteria:
                tasks = TASK.findall(stem)
                criteria = [{'criterion':f'第{n}问：{task.strip()}','score':2} for n,task in tasks]
                numbered = re.findall(r'([①②③④⑤⑥])([^①②③④⑤⑥\n]+)',stem)
                if numbered:
                    criteria = [{'criterion':f'第{n}项：{task.strip()}','score':2} for n,task in numbered]
            if not criteria:
                criteria=[{'criterion':'写出合法条件与所用方法','score':2},
                          {'criterion':'完成推导并给出符合条件的结论','score':4}]
            row.update(reference_answer=explanation,
                       solution_steps=[re.sub(r'^(?:解|证明|解析)\s*[:：]?\s*','',b['text']).strip() for b in explanation_blocks if b['text'].strip()],
                       rubric=criteria,max_score=sum(c['score'] for c in criteria),
                       rubric_status='pending_review',
                       rubric_basis='原题分问标注；未标分时为2分/问的草案，需人工校准')
            row['review_notes'].append('rubric 是审核草案，不进行自动评分；分值与评分点须人工确认。')
            results.append(_finish(row))
            # Some worked examples contain several independent "已知...求..."
            # questions, each with its own numbered solution. Split only when
            # every subitem restates its conditions; never split shared context.
            tasks=[]
            for b in stem_blocks:
                task=re.search(r'[（(](\d+)[）)]\s*((?:已知|设函数).+)',b['text'])
                if task: tasks.append((task[1],b,task[2]))
            first_prefix = re.split(r'[（(]1[）)]',stem_blocks[0]['text'],maxsplit=1)[0]
            independent = len(tasks)>=2 and re.fullmatch(r'(?:例|跟踪训练)\s*\d+\s*',first_prefix)
            if independent:
                solution_positions=[]
                for offset,b in enumerate(explanation_blocks):
                    text=re.sub(r'^(?:解|证明|解析)\s*[:：]?\s*','',b['text'])
                    marker=re.match(r'[（(](\d+)[）)]',text)
                    if marker: solution_positions.append((marker[1],offset))
                if [n for n,_,_ in tasks]==[n for n,_ in solution_positions]:
                    for pos,(number,task_block,task_text) in enumerate(tasks):
                        begin=solution_positions[pos][1]
                        finish=solution_positions[pos+1][1] if pos+1<len(tasks) else len(explanation_blocks)
                        steps=explanation_blocks[begin:finish]
                        selected_blocks=[task_block]+steps
                        solution='\n'.join(b['text'] for b in steps).strip()
                        sub=_common(path,selected_blocks,0,len(selected_blocks),task_text,solution,'subjective')
                        sub.update(reference_answer=solution,solution_steps=[b['text'] for b in steps if b['text'].strip()],
                                   rubric=[{'criterion':'正确使用题设条件与方法','score':2},
                                           {'criterion':'推导解析式并说明适用范围','score':4}],max_score=6,
                                   rubric_status='pending_review',rubric_basis='独立小问的评分草案，须人工确认',
                                   source_subquestion=number,
                                   source_ranges=[[task_block['index'],task_block['index']],
                                                  [steps[0]['index'],steps[-1]['index']]])
                        sub['review_notes'].append('从独立小问提取；本小问已重述完整条件，不继承其他小问。评分表为草案。')
                        results.append(_finish(sub))
    return results
