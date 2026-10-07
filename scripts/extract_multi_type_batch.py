"""Scan the 15 supplied DOCX files, write reviewed batches and original-math DOCX."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.source_extractors.docx_multi_type_extractor import extract_multi_type_questions
from services.question_validator import validate_candidate

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def write_readable_docx(rows,output):
    """Copy selected source paragraphs, preserving native OMML fractions/scripts."""
    ET.register_namespace('w',W[1:-1])
    doc = ET.Element(W+'document')
    body = ET.SubElement(doc,W+'body')
    def paragraph(text):
        p=ET.SubElement(body,W+'p')
        r=ET.SubElement(p,W+'r')
        props=ET.SubElement(r,W+'rPr')
        ET.SubElement(props,W+'rFonts',{W+'ascii':'Cambria',W+'eastAsia':'宋体'})
        ET.SubElement(r,W+'t').text=text
    paragraph('函数专题多题型 · 待人工审核')
    paragraph(f'共{len(rows)}题，全部 reviewed，未 approved；来源许可与数学内容待核对。')
    paragraph('以下原文数学公式保留 Word 原生公式。主观题评分表为草案，请人工确认。')
    cache={}
    for n,row in enumerate(rows,1):
        p=ET.SubElement(body,W+'p'); r=ET.SubElement(p,W+'r')
        ET.SubElement(r,W+'br',{W+'type':'page'})
        paragraph(f"第{n}题 · {row['id']} · {row['question_type']}")
        paragraph('来源：'+row['source_file']+' / '+row['source_locator'])
        source=ROOT/row['source_file']
        if str(source) not in cache:
            with ZipFile(source) as z:
                cache[str(source)]=list(ET.fromstring(z.read('word/document.xml')).find(W+'body').iter(W+'p'))
        start,end=map(int,re.search(r'paragraphs (\d+)–(\d+)',row['source_locator']).groups())
        ranges=row.get('source_ranges',[[start,end]])
        for begin,finish in ranges:
            for original in cache[str(source)][begin-1:finish]: body.append(deepcopy(original))
        paragraph('主要知识点：'+row['primary_knowledge_point_id']+f"；难度：{row['difficulty']}（草标）")
        if row['question_type']=='fill_blank':
            paragraph('判分答案类型：'+row['answer_type'])
            paragraph('接受答案：'+json.dumps(row['accepted_answers'],ensure_ascii=False))
        else:
            paragraph(f"评分草案（总分 {row['max_score']}）：")
            for criterion in row['rubric']:paragraph(f"{criterion['criterion']}：{criterion['score']}分")
            paragraph('评分依据：'+row['rubric_basis'])
        for note in row['review_notes']:paragraph('审核提醒：'+note)
    ET.SubElement(body,W+'sectPr')
    types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types)
        z.writestr('_rels/.rels',rels)
        z.writestr('word/document.xml',ET.tostring(doc,encoding='utf-8',xml_declaration=True))


def build_batch():
    sources=sorted((ROOT/'data/raw_sources/function').glob('*.docx'))
    sources=[p for p in sources if not p.name.startswith('~$')]
    if len(sources)!=15: raise ValueError('预期15份本地 DOCX，拒绝扫描其他目录。')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    rows=[]
    for p in sources:rows.extend(extract_multi_type_questions(p.relative_to(ROOT)))
    selected={};excluded=[];seen=set()
    for kind,limit in [('fill_blank',25),('subjective',18)]:
        pool=[r for r in rows if r['question_type']==kind]
        clean=[r for r in pool if r['extraction_status']=='complete' and validate_candidate(r)['can_approve']]
        # Spread across files and simpler questions first, deterministically.
        buckets={p.name:[] for p in sources}
        for r in sorted(clean,key=lambda r:(r['difficulty'],len(r['explanation']),r['id'])):
            buckets[Path(r['source_file']).name].append(r)
        picks=[]
        while len(picks)<limit and any(buckets.values()):
            for bucket in buckets.values():
                if bucket and len(picks)<limit:
                    r=bucket.pop(0)
                    if r['fingerprint'] not in seen:
                        seen.add(r['fingerprint']); picks.append(r)
        selected[kind]=picks
        ids={r['id'] for r in picks}
        excluded.extend(r for r in pool if r['id'] not in ids)
    outputs=[]
    for kind,picks in selected.items():
        stem='function_'+kind+'_batch_001'
        jsonl=ROOT/'data/question_bank/candidates'/(stem+'.jsonl')
        docx=ROOT/'reports'/(stem+'_可读版.docx')
        outputs.extend([jsonl,docx])
    if any(p.exists() for p in outputs):raise FileExistsError('候选快照或可读版已存在，拒绝覆盖审核依据。')
    for kind,picks in selected.items():
        stem='function_'+kind+'_batch_001'
        jsonl=ROOT/'data/question_bank/candidates'/(stem+'.jsonl')
        jsonl.parent.mkdir(parents=True,exist_ok=True)
        jsonl.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in picks),encoding='utf-8')
        write_readable_docx(picks,ROOT/'reports'/(stem+'_可读版.docx'))
    audit=ROOT/'reports/multi_type_extraction_audit.json'
    report={'source_files_scanned':len(sources),'source_sha256':hashes,
            'recognized':dict(Counter(r['question_type'] for r in rows)),
            'selected':{k:len(v) for k,v in selected.items()},
            'excluded':[{'id':r['id'],'source_file':r['source_file'],'source_locator':r['source_locator'],
                         'question_type':r['question_type'],'errors':r['validation_errors'],
                         'warnings':r['validation_warnings'],'extraction_status':r['extraction_status']} for r in excluded],
            'all_selected_reviewed':all(r['quality_status']=='reviewed' for v in selected.values() for r in v),
            'automatically_approved':0,'source_files_unchanged':hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    audit.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('source_sha256','excluded')}


if __name__=='__main__':
    print(json.dumps(build_batch(),ensure_ascii=True,indent=2))
