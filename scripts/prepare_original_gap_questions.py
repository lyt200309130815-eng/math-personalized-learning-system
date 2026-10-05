"""Offline original function questions: deterministic checks, never approval."""

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.question_deduplication import DuplicateIndex
from services.question_bank_coverage import build_coverage_report
from services.question_review import atomic_write, read_jsonl
from services.question_validator import content_fingerprint, load_taxonomy, validate_candidate

OUTPUT = ROOT / 'data/question_bank/candidates/function_batch_003_original.jsonl'


def build_original_questions():
    """Eleven authored items; source locators refer to originals, not DOCX pages."""
    specs = [
        ('K001', 1, '设集合A={1，2，3}，B={a，b}。下列从A到B的对应关系中，能构成函数的是（　　）。',
         ['1→a，2→b，3→a', '1同时对应a和b，2→a，3→b', '1→a，2→b，3没有对应元素', '1→a，2没有对应元素，3→b'], 'A',
         '函数要求A中的每个元素在B中都有且只有一个对应元素。A项满足这一条件，允许不同自变量对应同一函数值。B项的1有两个对应值；C、D项分别有元素3、2没有对应值，故选A。',
         ['concept_understanding'], ['definition'], [], []),
        ('K001', 2, '已知函数f(x)=x，定义域为R。下列函数中，与f表示同一个函数的是（　　）。',
         ['g(t)=t，定义域为R', 'g(x)=x，定义域为[0，+∞)', 'g(x)=|x|，定义域为R', 'g(x)=x+1，定义域为R'], 'A',
         '判断同一函数要比较定义域和对应法则，自变量的字母名称不影响函数。A项与f的定义域、对应法则一致。B项定义域不同；C项在负数处对应值不同；D项对应法则不同，故选A。',
         ['concept_understanding', 'logical_reasoning'], ['definition', 'special_value'], [], []),
        ('K007', 1, '下列解析式中，表示二次函数的是（　　）。',
         ['y=3x²−2x+1', 'y=2x+1', 'y=1/x', 'y=x³'], 'A',
         '二次函数的基本形式是y=ax²+bx+c，其中a≠0。A项是该形式且二次项系数为3。B项是一次函数，C项是反比例函数，D项为三次多项式函数，故选A。',
         ['concept_understanding'], ['definition'], [], []),
        ('K007', 2, '二次函数f(x)=x²−6x+5的图象的对称轴是（　　）。',
         ['x=−3', 'x=3', 'x=5', 'x=−5'], 'B',
         '对二次函数ax²+bx+c，对称轴为x=−b/(2a)。这里a=1，b=−6，所以对称轴为x=3。也可配方得f(x)=(x−3)²−4，故选B。',
         ['calculation', 'graph_analysis'], ['symmetry', 'substitution'], [], []),
        ('K007', 1, '二次函数f(x)=2(x+1)²−3的图象的顶点坐标是（　　）。',
         ['(1，−3)', '(−1，3)', '(−1，−3)', '(1，3)'], 'C',
         '顶点式a(x−h)²+k的顶点为(h，k)。因为x+1=x−(−1)，本题h=−1、k=−3，所以顶点为(−1，−3)，故选C。',
         ['concept_understanding', 'graph_analysis'], ['definition'], [], []),
        ('K007', 2, '关于抛物线y=−2(x−1)²+3的开口方向和顶点位置，下列说法正确的是（　　）。',
         ['开口向下，顶点在第一象限', '开口向上，顶点在第一象限', '开口向下，顶点在第二象限', '开口向上，顶点在第二象限'], 'A',
         '二次项系数−2<0，所以开口向下。由顶点式可知顶点是(1，3)，横、纵坐标都大于0，因此顶点在第一象限。只有A项同时满足，故选A。',
         ['concept_understanding', 'graph_analysis'], ['definition', 'special_value'], [], []),
        ('K007', 3, '某二次函数的图象经过点(0，1)、(1，0)、(2，3)。它的解析式是（　　）。',
         ['y=2x²−3x+1', 'y=x²−2x+1', 'y=−2x²+x+1', 'y=2x²+3x+1'], 'A',
         '设y=ax²+bx+c，且a≠0。代入(0，1)得c=1；代入(1，0)得a+b=−1；代入(2，3)得4a+2b=2。联立后得到a=2、b=−3，所以y=2x²−3x+1。代入三个点均成立，其余选项至少不满足一个点，故选A。',
         ['calculation', 'logical_reasoning'], ['substitution'], [], []),
        ('K009', 1, '按照指数函数y=aˣ（a>0且a≠1）的定义，下列函数中属于指数函数的是（　　）。',
         ['y=1ˣ', 'y=(1/3)ˣ', 'y=(−2)ˣ', 'y=2x²'], 'B',
         '指数函数要求底数a>0且a≠1，自变量在指数位置。B项底数为1/3，符合条件。A项底数为1，C项底数为负数，均不符合；D项自变量不在指数位置，故选B。',
         ['concept_understanding'], ['definition'], [], []),
        ('K009', 2, '指数函数y=(1/2)ˣ在R上的增减性以及图象经过的点，正确的是（　　）。',
         ['单调递减，经过(0，1)', '单调递增，经过(0，1)', '单调递减，经过(0，0)', '单调递增，经过(0，0)'], 'A',
         '因为底数1/2在0与1之间，指数函数在R上单调递减；x=0时，(1/2)⁰=1，所以图象经过(0，1)。两项性质都正确的是A，故选A。',
         ['concept_understanding', 'graph_analysis'], ['definition', 'special_value'], [], []),
        ('K005', 2, '函数f(x)=x²的定义域限定为(0，+∞)。关于该函数的奇偶性，下列说法正确的是（　　）。',
         ['是奇函数', '是偶函数', '既是奇函数又是偶函数', '既不是奇函数，也不是偶函数'], 'D',
         '判断奇偶性首先检查定义域是否关于原点对称。本题定义域为(0，+∞)，1在定义域内而−1不在，因此定义域不关于原点对称。不满足奇函数或偶函数的定义，故选D；不能仅凭解析式x²就判断为偶函数。',
         ['concept_understanding', 'logical_reasoning'], ['definition', 'symmetry'], [], []),
        ('K014', 2, '将方程x²=x+2转化为函数f(x)=x²与g(x)=x+2的图象交点问题。两图象交点的横坐标组成的集合是（　　）。',
         ['{−2，1}', '{−1，2}', '{1，2}', '{−1，−2}'], 'B',
         '交点处同一横坐标对应的两个函数值相等，所以交点横坐标满足x²=x+2。移项并因式分解得(x−2)(x+1)=0，解得x=2或x=−1。此时两交点为(2，4)、(−1，1)，横坐标集合为{−1，2}，故选B。',
         ['logical_reasoning', 'calculation', 'graph_analysis'], ['substitution', 'zero_analysis'], ['K007'], ['K007']),
    ]
    rows, numbers = [], Counter()
    for ordinal, (key, difficulty, stem, options, answer, explanation, abilities, methods, related, prerequisites) in enumerate(specs, 1):
        numbers[(key, difficulty)] += 1
        identifier = f'Q-ORG-F-{key}-D{difficulty}-{numbers[(key, difficulty)]:03d}'
        row = dict(id=identifier, stem=stem, options=dict(zip('ABCD', options)), answer=answer,
                   explanation=explanation, taxonomy_version='function_v2',
                   primary_knowledge_point_id=key, related_knowledge_point_ids=related,
                   question_prerequisite_ids=prerequisites, difficulty=difficulty,
                   ability_tags=abilities, method_tags=methods, estimated_time=difficulty*60,
                   source_type='original', source_ref='V0.8G-original-gap-fill',
                   source_file='data/question_bank/candidates/function_batch_003_original.jsonl',
                   source_section='函数专题原创定向补缺', source_question_number=str(ordinal),
                   source_locator='原创题编号：'+identifier, extraction_status='complete',
                   question_type='single_choice',
                   extraction_warnings=[], image_resources=[], quality_status='reviewed',
                   annotation_status='pending_teacher_review', review_notes=['原创候选题，程序验证不代替人工审核，未批准。'],
                   version=1)
        row['fingerprint'] = content_fingerprint(row)
        row['validation_notes'] = verify_original_math(row)
        checked = validate_candidate(row)
        if not checked['can_approve']:
            raise ValueError(f"{identifier}: {checked['errors'] + checked['warnings']}")
        rows.append(row)
    return rows


def verify_original_math(row):
    """Verify all four choices against finite maps or explicit algebraic models."""
    key = (row['primary_knowledge_point_id'], row['difficulty'], row['id'].rsplit('-', 1)[1])
    if key == ('K001', 1, '001'):
        maps = [{1:['a'],2:['b'],3:['a']}, {1:['a','b'],2:['a'],3:['b']},
                {1:['a'],2:['b']}, {1:['a'],3:['b']}]
        truths = [set(m) == {1,2,3} and all(len(v)==1 and v[0] in {'a','b'} for v in m.values()) for m in maps]
        note = '逐一检查有限映射：每个自变量恰有一个合法对应值。'
    elif key == ('K001', 2, '001'):
        # B differs by domain; counterexamples at -1 and 0 reject C and D.
        truths = [True, False, abs(-1)==-1, 0+1==0]
        note = '比较定义域；使用x=-1、x=0排除对应法则不同的选项。'
    elif key == ('K007', 1, '001'):
        truths = [degree == 2 for degree in (2,1,-1,3)]
        note = '检查多项式最高次数及非零二次项系数。'
    elif key == ('K007', 2, '001'):
        axis = -(-6)/(2*1)
        truths = [value == axis for value in (-3,3,5,-5)]
        note = '对称轴−b/(2a)=3；四个选项仅x=3成立。'
    elif key == ('K007', 1, '002'):
        truths = [vertex == (-1,-3) for vertex in ((1,-3),(-1,3),(-1,-3),(1,3))]
        note = '从顶点式读取(h,k)=(-1,-3)，检查所有选项。'
    elif key == ('K007', 2, '002'):
        actual = (-2<0, 1>0 and 3>0)
        truths = [choice == actual for choice in ((True,True),(False,True),(True,False),(False,False))]
        note = '系数−2<0，顶点(1,3)位于第一象限。'
    elif key == ('K007', 3, '001'):
        models = [(2,-3,1),(1,-2,1),(-2,1,1),(2,3,1)]
        truths = [a!=0 and all(a*x*x+b*x+c==y for x,y in ((0,1),(1,0),(2,3))) for a,b,c in models]
        note = '逐式代入(0,1)、(1,0)、(2,3)，唯一满足者为2x²−3x+1。'
    elif key == ('K009', 1, '001'):
        truths = [base>0 and base!=1 and variable_exponent for base,variable_exponent in ((1,True),(1/3,True),(-2,True),(2,False))]
        note = '检查底数为正且不等于1，并检查自变量是否在指数位置。'
    elif key == ('K009', 2, '001'):
        actual = (0 < 1/2 < 1, (1/2)**0)
        truths = [choice == actual for choice in ((True,1),(False,1),(True,0),(False,0))]
        note = '使用指数函数底数分类定理，并直接计算x=0的函数值。'
    elif key == ('K005', 2, '001'):
        symmetric = (1>0) == (-1>0)
        truths = [symmetric, symmetric, symmetric, not symmetric]
        note = '用1与−1构造定义域不对称的反例，先检查奇偶性的必要条件。'
    elif key == ('K014', 2, '001'):
        choices = [(-2,1),(-1,2),(1,2),(-1,-2)]
        truths = [set(values)=={-1,2} and all(x*x==x+2 for x in values) for values in choices]
        note = '因式分解(x−2)(x+1)=0，并逐个代入交点方程检查。'
    else:
        raise ValueError('未定义该原创题的数学验证。')
    correct = [letter for letter, truth in zip('ABCD', truths) if truth]
    if correct != [row['answer']]:
        raise ValueError(f"{row['id']} 数学验证失败：{correct}")
    return [note, '确定性验证：四个选项中恰有一个正确答案，且与标准答案一致。', '程序验证不等于人工审核；保持reviewed。']


def write_readable_docx(rows, output):
    """Originals already use readable Unicode math; no Word Equation needed."""
    w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    ET.register_namespace('w', w)
    doc = ET.Element(f'{{{w}}}document'); body = ET.SubElement(doc, f'{{{w}}}body')
    names = {p['id']:p['name'] for p in load_taxonomy()['knowledge_points']}
    def paragraph(text, bold=False):
        p = ET.SubElement(body,f'{{{w}}}p'); r=ET.SubElement(p,f'{{{w}}}r')
        props=ET.SubElement(r,f'{{{w}}}rPr')
        ET.SubElement(props,f'{{{w}}}rFonts',{f'{{{w}}}ascii':'Cambria',f'{{{w}}}eastAsia':'宋体'})
        ET.SubElement(props,f'{{{w}}}sz',{f'{{{w}}}val':'24'})
        if bold: ET.SubElement(props,f'{{{w}}}b')
        ET.SubElement(r,f'{{{w}}}t').text=text
    paragraph('高中数学函数专题 · 原创定向补缺题',True)
    paragraph('共11道待人工审核的单项选择题。程序验证不能代替人工审核，所有题目尚未批准。')
    for n,row in enumerate(rows,1):
        p=ET.SubElement(body,f'{{{w}}}p'); r=ET.SubElement(p,f'{{{w}}}r'); ET.SubElement(r,f'{{{w}}}br',{f'{{{w}}}type':'page'})
        paragraph(f'第{n}题',True); paragraph(row['stem'])
        for letter in 'ABCD': paragraph(letter+'. '+row['options'][letter])
        paragraph('答案：'+row['answer'],True); paragraph('解析：'+row['explanation'])
        paragraph('主要知识点：'+names[row['primary_knowledge_point_id']])
        paragraph(f"难度：{row['difficulty']}级（1—5级）")
        paragraph('相关知识点：'+('、'.join(names[k] for k in row['related_knowledge_point_ids']) or '无'))
        paragraph('题级前置：'+('、'.join(names[k] for k in row['question_prerequisite_ids']) or '无'))
        paragraph('来源：自主原创函数专题补缺题；等待人工审核。')
    section=ET.SubElement(body,f'{{{w}}}sectPr')
    ET.SubElement(section,f'{{{w}}}pgSz',{f'{{{w}}}w':'11906',f'{{{w}}}h':'16838'})
    types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types); z.writestr('_rels/.rels',rels)
        z.writestr('word/document.xml',ET.tostring(doc,encoding='utf-8',xml_declaration=True))


def prepare_outputs():
    gold1=read_jsonl(ROOT/'data/question_bank/approved/function_batch_001_approved.jsonl')
    gold2=read_jsonl(ROOT/'data/question_bank/approved/function_batch_002_approved.jsonl')
    if len(gold2)!=26 or any(not validate_candidate(q)['can_approve'] or q['quality_status']!='approved' for q in gold2):
        raise ValueError('Batch 002尚未完成批准。')
    rows=build_original_questions()
    index=DuplicateIndex(gold1+gold2)
    for row in rows:
        if index.reasons(row): raise ValueError('原创题与已有题重复：'+row['id'])
        index.add(row)
    report_path=ROOT/'reports/question_bank_coverage_after_original_batch.md'
    docx=ROOT/'reports/function_batch_003_original_可读版.docx'
    if any(path.exists() for path in (OUTPUT,report_path,docx)):
        raise FileExistsError('原创题输出已存在，拒绝覆盖审核快照。')
    current=build_coverage_report(gold1+gold2)
    # Hypothetical copies only: never promote the original rows or export them as approved.
    hypothetical=[{**deepcopy(q),'quality_status':'approved'} for q in rows]
    projected=build_coverage_report(gold1+gold2+hypothetical)
    c1=Counter(q['primary_knowledge_point_id'] for q in gold1)
    c2=Counter(q['primary_knowledge_point_id'] for q in gold2)
    c3=Counter(q['primary_knowledge_point_id'] for q in rows)
    lines=['# 原创补缺题覆盖预测','',
           'Batch 001 approved=29；Batch 002 approved=26；Batch 003 original reviewed=11。当前正式批准55题；原创题尚未人工批准。',
           'projected_total仅是假设原创题未来全部批准后的覆盖预测，不用于正式训练，也不修改mastery。',
           '门槛：每节点至少3题、至少1道难度1–2、至少1道难度2–3；难度2可同时满足两类要求。','',
           '| 知识点 | Batch001 approved | Batch002 approved | Batch003 reviewed | current_approved | new_reviewed | projected_total | 当前状态 | 预测状态 |',
           '|---|---:|---:|---:|---:|---:|---:|---|---|']
    for actual,prediction in zip(current['points'],projected['points']):
        k=actual['knowledge_point_id']
        lines.append(f"| {k} {actual['knowledge_point_name']} | {c1[k]} | {c2[k]} | {c3[k]} | {actual['approved_count']} | {c3[k]} | {prediction['approved_count']} | {actual['status']} | {prediction['status']} |")
    lines+=['','当前不足门槛：'+ '、'.join(p['knowledge_point_id'] for p in current['points'] if p['gaps']),
            '预测不足门槛：'+ ('、'.join(p['knowledge_point_id'] for p in projected['points'] if p['gaps']) or '无'),
            '', '## 原创题难度分布','',str(dict(sorted(Counter(q['difficulty'] for q in rows).items()))),
            '', '真实数据库未迁移；原创题没有批准，也没有导入任何数据库。','']
    atomic_write(OUTPUT,''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in rows))
    atomic_write(report_path,'\n'.join(lines))
    write_readable_docx(rows,docx)
    return rows


if __name__=='__main__':
    result=prepare_outputs()
    print('Prepared original reviewed questions:',len(result))
