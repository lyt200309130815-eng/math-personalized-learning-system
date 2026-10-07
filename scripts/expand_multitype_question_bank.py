"""Read-only V1.0D.1 expansion artifacts; never approves or imports questions."""
from collections import Counter
from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from database.database import get_approved_questions
from services.question_validator import validate_candidate, load_taxonomy
from services.source_extractors.docx_expansion_extractor import extract_expansion_questions
from scripts.inspect_multitype_sources import protected_snapshot

KINDS=('single_choice','multiple_choice','fill_blank','subjective')
BATCHES={'multiple_choice':'001','fill_blank':'002','subjective':'002'}
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def read_rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def readable_math(text):
    # Display-only, unambiguous small powers/subscripts; source OMML is retained.
    text=re.sub(r'\^\(([0-9]+)\)',lambda m:m[1].translate(str.maketrans('0123456789','⁰¹²³⁴⁵⁶⁷⁸⁹')),text)
    text=re.sub(r'_\(([0-9]+)\)',lambda m:m[1].translate(str.maketrans('0123456789','₀₁₂₃₄₅₆₇₈₉')),text)
    return text.replace('sqrt(', '√(')


def write_word(rows,output):
    """Copy original mathematical paragraphs and add explicit human review fields."""
    ET.register_namespace('w',W[1:-1])
    doc=ET.Element(W+'document');body=ET.SubElement(doc,W+'body')
    def paragraph(text,bold=False):
        p=ET.SubElement(body,W+'p');r=ET.SubElement(p,W+'r');props=ET.SubElement(r,W+'rPr')
        ET.SubElement(props,W+'rFonts',{W+'ascii':'Cambria',W+'eastAsia':'宋体'})
        if bold: ET.SubElement(props,W+'b')
        ET.SubElement(r,W+'t').text=readable_math(str(text))
    paragraph('V1.0D.1 函数多题型 · 人工审核版',True)
    paragraph(f'共 {len(rows)} 题；全部待审，未批准、未导入。标签与难度为草标。')
    paragraph('原文保留 Word 原生数学公式；评分点为系统草案，不是原资料官方评分细则。')
    cache={};names={p['id']:p['name'] for p in load_taxonomy()['knowledge_points']}
    for index,row in enumerate(rows,1):
        p=ET.SubElement(body,W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'br',{W+'type':'page'})
        paragraph(f"第{index}题 · {row['id']}",True)
        paragraph('来源：'+row['source_file']+' / '+row['source_locator'])
        paragraph('题目、选项与原标准解答（以下为原文，数学公式未改写）：',True)
        source=ROOT/row['source_file']
        if source not in cache:
            with ZipFile(source) as z:
                cache[source]=list(ET.fromstring(z.read('word/document.xml')).find(W+'body').iter(W+'p'))
        begin,end=map(int,re.search(r'paragraphs (\d+)–(\d+)',row['source_locator']).groups())
        for first,last in row.get('source_ranges',[[begin,end]]):
            for original in cache[source][first-1:last]: body.append(deepcopy(original))
        if row['question_type']=='multiple_choice':
            paragraph('正确答案集合：'+'、'.join(row['correct_answers']),True)
            paragraph('判分：全部选对得分；不计部分分。')
        elif row['question_type']=='fill_blank':
            paragraph('标准答案：'+row['canonical_answer'],True)
            paragraph('可接受答案：'+'；'.join(row['accepted_answers']))
            paragraph('答案类型：'+row['answer_type'])
        else:
            paragraph('小问结构：',True)
            for sub in row['sub_questions']:
                paragraph(f"({sub['id']}) {sub['stem']}（草案 {sub['max_score']} 分）")
            paragraph('参考解答请核对上方原文；对应小问：',True)
            for number,answer in row['reference_answers_by_subquestion'].items():
                paragraph(f'({number}) '+answer)
            paragraph(f"评分点（总分 {row['max_score']}，系统草案）：",True)
            for criterion in row['rubric']:
                paragraph(f"({criterion['sub_question']}) {criterion['criterion']}：{criterion['score']:.3g}分")
            paragraph('rubric_source：derived_for_system；需教师逐项确认分值和方法。')
        key=row['primary_knowledge_point_id']
        paragraph(f"知识点：{key} {names[key]}；难度：{row['difficulty']}（待确认）",True)
        paragraph('审核记录：□批准 □修订 □拒绝；审核人：________ 日期：________')
        paragraph('备注：________________________________________________')
    section=ET.SubElement(body,W+'sectPr')
    ET.SubElement(section,W+'pgSz',{W+'w':'11906',W+'h':'16838'})
    ET.SubElement(section,W+'pgMar',{W+'top':'1134',W+'bottom':'1134',W+'left':'1134',W+'right':'1134'})
    types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types);z.writestr('_rels/.rels',rels)
        z.writestr('word/document.xml',ET.tostring(doc,encoding='utf-8',xml_declaration=True))


def coverage_report(approved,selected,audit):
    lines=['# V1.0D.1 多题型题库覆盖报告','',
           '只扫描15份本地DOCX；新题全部 reviewed。真实数据库、approved 文件和历史 attempts 均未修改。',
           '为了保留旧批次，填空/解答题使用 batch_002，多选使用 batch_001。',
           '这是重新扫描后的审核批次；复用上一版尚未批准的来源题会明确统计，不计作正式新增。','',
           f"本轮可靠候选：{json.dumps({k:len(v) for k,v in selected.items()},ensure_ascii=False)}。",'']
    for title,rows in [('当前 approved 静态题（含6道旧种子题）',approved),('本轮 reviewed 候选',[r for v in selected.values() for r in v]),('approved + reviewed 覆盖投影',approved+[r for v in selected.values() for r in v])]:
        lines += ['## '+title,'','| 知识点 | single_choice | multiple_choice | fill_blank | subjective | d1 | d2 | d3 | d4 | d5 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for point in load_taxonomy()['knowledge_points']:
            subset=[r for r in rows if (r.get('primary_knowledge_point_id') or r.get('knowledge_point_id'))==point['id']]
            counts=Counter(r.get('question_type','single_choice') for r in subset);ds=Counter(r['difficulty'] for r in subset)
            lines.append('| '+point['id']+' '+point['name']+' | '+' | '.join(str(counts[k]) for k in KINDS)+' | '+' | '.join(str(ds[d]) for d in range(1,6))+' |')
        lines+=['', '题型总数：'+str(dict(Counter(r.get('question_type','single_choice') for r in rows))),
                '难度总数：'+str(dict(sorted(Counter(r['difficulty'] for r in rows).items()))),'']
    lines+=['## 长期覆盖缺口（投影，不表示已批准）','','| 知识点 | 选择/多选距3题 | 填空距3题 | 大题距1–2题 |','|---|---:|---:|---|']
    combined=approved+[r for v in selected.values() for r in v]
    suitable={'K003','K004','K007','K012','K013','K014','K015'}
    for point in load_taxonomy()['knowledge_points']:
        counts=Counter(r.get('question_type','single_choice') for r in combined if (r.get('primary_knowledge_point_id') or r.get('knowledge_point_id'))==point['id'])
        sub=f"{max(0,1-counts['subjective'])}–{max(0,2-counts['subjective'])}" if point['id'] in suitable else '按教学适用性安排'
        lines.append(f"| {point['id']} | {max(0,3-counts['single_choice']-counts['multiple_choice'])} | {max(0,3-counts['fill_blank'])} | {sub} |")
    lines+=['','## 提取审计','',f"识别题型：{audit['recognized']}。",f"独立风险计数（可以重叠）：{audit['risk_counts']}。",
            f"互斥 extraction_status：{audit['status_counts']}。",f"与旧待审多题型来源重合：{audit['previous_reviewed_overlap']}。",'完整排除原因与来源位置见 function_multitype_extraction_audit.json。',
            'K012图象与K015建模缺口不能靠缺图题填补。评分草案不用于自动判大题分数。','']
    return '\n'.join(lines)


def build():
    before=protected_snapshot()
    sources=sorted((ROOT/'data/raw_sources/function').glob('*.docx'))
    if len(sources)!=15: raise ValueError('必须恰好15份本地DOCX。')
    # Read every approved payload, in addition to the live static bank.
    gold=[q for p in sorted((ROOT/'data/question_bank/approved').glob('*.jsonl')) for q in read_rows(p)]
    approved=get_approved_questions(database_path=ROOT/'math_ai.db',taxonomy_version='function_v2')
    approved=[q for q in approved if q['source_type']!='generated_template']
    old_multi=[q for kind in ('fill_blank','subjective') for q in read_rows(ROOT/f'data/question_bank/candidates/function_{kind}_batch_001.jsonl')]
    old_sources={(q['source_file'],q['source_locator']) for q in old_multi}
    rows=[q for p in sources for q in extract_expansion_questions(p.relative_to(ROOT))]
    excluded=[];selected={};seen={q['fingerprint'] for q in gold};selected_ranges=[]
    for kind,limit in [('multiple_choice',20),('fill_blank',35),('subjective',20)]:
        pool=[q for q in rows if q['question_type']==kind]
        clean=[q for q in pool if q['extraction_status']=='complete' and validate_candidate(q)['can_approve']]
        # Prefer intact full subjective questions over independent subitems of the same parent.
        clean.sort(key=lambda q:(bool(q.get('source_subquestion')),q['difficulty'],q['id']))
        buckets={p.name:[] for p in sources}
        for q in clean:buckets[Path(q['source_file']).name].append(q)
        picks=[]
        while len(picks)<limit and any(buckets.values()):
            for bucket in buckets.values():
                if not bucket or len(picks)>=limit: continue
                q=bucket.pop(0)
                begin,end=map(int,re.search(r'paragraphs (\d+)–(\d+)',q['source_locator']).groups())
                if q['fingerprint'] in seen: continue
                if kind=='subjective' and any(f==q['source_file'] and not (end<a or begin>b) for f,a,b in selected_ranges): continue
                seen.add(q['fingerprint']);picks.append(q)
                if kind=='subjective':selected_ranges.append((q['source_file'],begin,end))
        selected[kind]=picks
        ids={q['id'] for q in picks}
        excluded.extend(q for q in pool if q['id'] not in ids)
    outputs=[]
    for kind,batch in BATCHES.items():
        stem=f'function_{kind}_batch_{batch}'
        outputs.extend([ROOT/f'data/question_bank/candidates/{stem}.jsonl',ROOT/f'data/question_bank/review_required/{stem}.jsonl',ROOT/f'reports/{stem}_可读版.docx'])
    outputs.extend([ROOT/'reports/function_multitype_question_bank_report.md',ROOT/'reports/function_multitype_extraction_audit.json'])
    if any(p.exists() for p in outputs): raise FileExistsError('输出已存在，拒绝覆盖任何审核批次。')
    for kind,picks in selected.items():
        stem=f'function_{kind}_batch_{BATCHES[kind]}'
        content=''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in picks)
        for folder in ('candidates','review_required'):
            path=ROOT/f'data/question_bank/{folder}/{stem}.jsonl';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        write_word(picks,ROOT/f'reports/{stem}_可读版.docx')
    def risks(q):
        body=q['stem']+'\n'+q['explanation']+'\n'+str(q.get('options',''))
        return {'formula_warning':bool(q['extraction_status']=='formula_warning' or '[公式待核]' in body or any('公式' in w or '表达式' in w for w in q['validation_warnings'])),
                'image_required':bool(q['image_resources'] or re.search(r'如图|下图|图中|图示|图所示|图象如',body)),
                'incomplete':bool(q['validation_errors'] or not q['explanation'])}
    audit={'stage':'V1.0D.1','source_files_scanned':15,'approved_jsonl_read':len(gold),'approved_static_count':len(approved),
           'recognized':dict(Counter(q['question_type'] for q in rows)),
           'selected':{k:len(v) for k,v in selected.items()},'status_counts':dict(Counter(q['extraction_status'] for q in rows)),
           'risk_counts':dict(Counter(k for q in rows for k,v in risks(q).items() if v)),
           'previous_reviewed_overlap':{kind:sum((q['source_file'],q['source_locator']) in old_sources for q in picks) for kind,picks in selected.items()},
           'excluded':[{'id':q['id'],'question_type':q['question_type'],'source_file':q['source_file'],'source_locator':q['source_locator'],
                        'extraction_status':q['extraction_status'],'errors':q['validation_errors'],'warnings':q['validation_warnings'],
                        'reason':'risk_or_validation' if q['extraction_status']!='complete' else 'batch_limit_or_duplicate_overlap'} for q in excluded],
           'automatically_approved':0,'production_imports':0,'ocr_called':False,'network_used':False}
    if protected_snapshot()!=before:raise AssertionError('保护文件或生产表发生变化。')
    audit.update(production_database_modified=False,historical_attempts_modified=False,protected_snapshot_unchanged=True)
    (ROOT/'reports/function_multitype_extraction_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'reports/function_multitype_question_bank_report.md').write_text(coverage_report(approved,selected,audit),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='excluded'},ensure_ascii=True,indent=2))


if __name__=='__main__':build()
