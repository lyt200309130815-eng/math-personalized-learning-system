"""Backup API -> additive migration -> real services; isolated database only."""
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from database.database import DATABASE_PATH, get_connection, get_approved_questions, record_attempt
from database.taxonomy_migration import migrate_function_v2, require_isolated
from services.question_review import read_jsonl, atomic_write
from services.question_bank_coverage import build_coverage_report
from services.mastery import calculate_student_mastery
from services.recommendation import generate_recommendation, recommend_questions


def load_gold():
    rows=[]
    for batch in ('001','002','003_original'):
        rows+=read_jsonl(ROOT/f'data/question_bank/approved/function_batch_{batch}_approved.jsonl')
    if len(rows)!=66: raise ValueError('金标准题总数必须为66。')
    return rows


def database_summary(path):
    with closing(get_connection(path,read_only=True)) as c:
        rows=[list(r) for r in c.execute('SELECT * FROM attempts ORDER BY id')]
        count=c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    return {'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'questions_count':count,
            'attempts_count':len(rows),'attempts_digest':hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


def backup_database(source, target):
    target=require_isolated(target)
    if target.exists(): raise FileExistsError('隔离数据库已存在，拒绝覆盖。')
    target.parent.mkdir(parents=True,exist_ok=True)
    with closing(get_connection(source,read_only=True)) as original, closing(get_connection(target)) as copy:
        original.backup(copy)


def final_coverage_report(gold):
    report=build_coverage_report(gold)
    if any(p['approved_count']<3 for p in report['points']): raise ValueError('知识点不足3题，停止集成。')
    lines=['# Function V2 最终金标准题覆盖报告','',
           'Batch 001：29；Batch 002：26；Batch 003 original：11；合计66道 approved。',
           '旧Q001–Q006另行保留并映射，不计入这66道新增金标准题。','',
           '| 知识点 | approved | d1 | d2 | d3 | d4 | d5 | 基础诊断题1–2 | 覆盖状态 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for p in report['points']:
        ds=' | '.join(str(p['difficulty_distribution'][str(i)]) for i in range(1,6))
        lines.append(f"| {p['knowledge_point_id']} {p['knowledge_point_name']} | {p['approved_count']} | {ds} | {p['foundation_count']} | {p['status']} |")
    for label,field in (('difficulty','difficulty'),('ability_tag','ability_tags'),('method_tag','method_tags')):
        count=Counter(q[field] for q in gold) if label=='difficulty' else Counter(tag for q in gold for tag in q[field])
        lines+=['',f'## {label}','', '| 项目 | 数量 |','|---|---:|']+[f'| {key} | {value} |' for key,value in sorted(count.items())]
    lines+=['','题量与难度覆盖已达标；具体推荐仍必须另查题级前置，不代表所有题立即可做。','']
    atomic_write(ROOT/'reports/function_v2_final_coverage_report.md','\n'.join(lines))
    return report


def simulate_learning_path(target):
    path=[]
    for key in ('K001','K002','K003'):
        available=get_approved_questions(key,database_path=target,taxonomy_version='function_v2')
        by_id={q['id']:q for q in available}
        eligible=recommend_questions('S_TEST_PATH',key,limit=50,database_path=target,taxonomy_version='function_v2')
        if not eligible: raise ValueError(f'{key}无满足前置的模拟训练题，停止演练。')
        questions=[by_id[q['id']] for q in eligible]
        for i in range(6):
            q=questions[i%len(questions)]
            correct=1 if i<5 else 0
            choice=q['answer'] if correct else next(k for k in 'ABCD' if k!=q['answer'])
            record_attempt('S_TEST_PATH',q['id'],choice,correct,2.0,database_path=target,taxonomy_version='function_v2')
        rec=generate_recommendation('S_TEST_PATH',database_path=target,taxonomy_version='function_v2')
        path.append({'trained':key,'next':rec['target_knowledge']['knowledge_point_id'],
                     'mastery':next(p for p in calculate_student_mastery('S_TEST_PATH',database_path=target,taxonomy_version='function_v2') if p['knowledge_point_id']==key)['mastery_score']})
    return path


def run_dry_run():
    gold=load_gold(); coverage=final_coverage_report(gold)
    before=database_summary(DATABASE_PATH)
    target=ROOT/'tmp/function_v2_dry_run.db'
    backup_database(DATABASE_PATH,target)
    first=migrate_function_v2(target,gold)
    repeat=migrate_function_v2(target,gold)
    assert first['inserted']==66 and repeat=={'inserted':0,'skipped':66}
    new=calculate_student_mastery('S_TEST_NEW',database_path=target,taxonomy_version='function_v2')
    assert len(new)==15 and all(p['mastery_score'] is None for p in new)
    start=generate_recommendation('S_TEST_NEW',database_path=target,taxonomy_version='function_v2')
    assert start['target_knowledge']['knowledge_point_id']=='K001' and start['recommended_questions']
    historical=calculate_student_mastery('S001',database_path=target,taxonomy_version='function_v2')
    assert next(p for p in historical if p['knowledge_point_id']=='K005')['mastery_score'] is None
    assert sum(p['attempt_count'] for p in historical)==before['attempts_count']
    path=simulate_learning_path(target)
    assert len(calculate_student_mastery('S001',database_path=target,taxonomy_version='function_v1'))==5
    assert database_summary(DATABASE_PATH)==before
    result={'real_before':before,'real_after':database_summary(DATABASE_PATH),'first_import':first,'repeat_import':repeat,
            'approved_count':66,'legacy_questions_preserved':before['questions_count'],'new_student_points':15,
            'S001_view':historical,'simulated_path':path,'real_database_modified':False,'real_attempts_modified':False}
    atomic_write(ROOT/'reports/function_v2_dry_run_validation.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__': run_dry_run()
