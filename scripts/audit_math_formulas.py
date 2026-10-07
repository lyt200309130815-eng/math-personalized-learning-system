"""Plan first; apply verified canonical notation with SQLite backup and rollback."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from database.database import get_connection,get_approved_questions
from services.math_normalizer import audit_question,FIELDS
from scripts.integrate_multitype_production import snapshot
from services.mastery import calculate_student_mastery


def digest(q):
    return hashlib.sha256(json.dumps({k:q.get(k) for k in FIELDS},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def mastery_digest(path):
    with closing(get_connection(path,read_only=True)) as c:
        students=[r[0] for r in c.execute('SELECT DISTINCT student_id FROM attempts ORDER BY student_id')]
    profiles={s:calculate_student_mastery(s,database_path=path,taxonomy_version='function_v2') for s in students}
    return hashlib.sha256(json.dumps(profiles,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def plan(path):
    questions=get_approved_questions(database_path=path,taxonomy_version='function_v2',include_untrainable=True)
    results=[]
    for q in questions:
        finding=audit_question(q)
        results.append({'question_id':q['id'],'question_type':q['question_type'],'original_digest':digest(q),**finding})
    safe=[r for r in results if r['changes'] and not r['issues']]
    manual=[r for r in results if r['issues']]
    target=ROOT/'data/question_bank/formula_fixes';target.mkdir(parents=True,exist_ok=True)
    (target/'safe_formula_fixes.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in safe),encoding='utf-8')
    review=ROOT/'data/question_bank/review_required';review.mkdir(parents=True,exist_ok=True)
    (review/'formula_manual_review.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in manual),encoding='utf-8')
    counts={'total':len(results),'normal':len(results)-len(safe)-len(manual),'safe_fixes':len(safe),'manual_review':len(manual),'abnormal':len(safe)+len(manual)}
    lines=['# function_v2 数学公式审核（V1.0D.4）','',json.dumps(counts,ensure_ascii=False),'',
           '唯一格式：普通文本 + 单个 `$...$` 标准LaTeX片段。禁止双重包装。安全修复不修改数学答案、题号、来源指纹或历史作答。',
           '', '原DOCX OMML序列化为 `(num)/(den)`、`base^(exp)`、`root(deg,arg)`，候选与数据库原样保留。旧renderer仅转换一部分，并把不可识别的LaTeX当普通Markdown转义，导致源码、花括号、双分隔符混杂。','']
    for r in results:
        if not r['changes'] and not r['issues']:continue
        lines += [f"## {r['question_id']} · {r['question_type']}",'',f"处理：{'formula_manual_review：暂停训练，回查原DOCX' if r['issues'] else '安全自动修复'}",'']
        for finding in r['issues']+r['changes']:
            lines += [f"字段：{finding['field']}；问题：{finding['issue']}；安全转换：{'YES' if finding['safe'] else 'NO'}",'', '原字符串：','```text',finding['original'],'```','']
            if finding.get('normalized') is not None:lines += ['标准化：','```text',finding['normalized'],'```','']
    (ROOT/'reports/function_v2_math_formula_audit.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (target/'formula_audit_plan.json').write_text(json.dumps({'counts':counts,'questions':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(counts),flush=True);return results,counts


def apply(path,results,*,allow_production=False):
    path=Path(path).resolve();production=path==(ROOT/'math_ai.db').resolve()
    if production and not allow_production:raise ValueError('正式库需要显式应用授权')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=(ROOT/'backups' if production else path.parent/'backups')/f'math_ai_before_v1_0d_4_{stamp}.sqlite3'
    backup.parent.mkdir(parents=True,exist_ok=True)
    with closing(get_connection(path,read_only=True)) as original,closing(get_connection(backup)) as target:
        before=snapshot(original);original.backup(target)
    profile_before=mastery_digest(backup)
    with closing(get_connection(path)) as c,c:
        c.execute('BEGIN IMMEDIATE')
        current={q['id']:q for q in get_approved_questions(database_path=path,taxonomy_version='function_v2',include_untrainable=True)}
        c.execute('''CREATE TABLE IF NOT EXISTS question_formula_status (
            question_id TEXT PRIMARY KEY REFERENCES questions(id),formula_status TEXT NOT NULL
            CHECK(formula_status IN ('valid','formula_warning','formula_manual_review','invalid')),
            original_digest TEXT NOT NULL,canonical_digest TEXT NOT NULL,findings_json TEXT NOT NULL,
            normalizer_version TEXT NOT NULL,audited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        for row in results:
            q=current[row['question_id']]
            if digest(q)!=row['original_digest'] and not (row['formula_status']=='valid' and digest(q)==digest(row['normalized'])):
                raise ValueError('修复计划已过期：'+q['id'])
            normalized=row['normalized'];status=row['formula_status']
            if status=='valid':
                if audit_question(normalized)['issues'] or audit_question(normalized)['changes']:raise ValueError('标准化不幂等：'+q['id'])
                c.execute('UPDATE questions SET stem=?,options=?,explanation=? WHERE id=?',
                          (normalized['stem'],json.dumps(normalized['options'],ensure_ascii=False) if normalized.get('options') else None,normalized['explanation'],q['id']))
                if normalized.get('hints') is not None:
                    c.execute('UPDATE question_variants SET hints_json=? WHERE question_id=?',(json.dumps(normalized['hints'],ensure_ascii=False),q['id']))
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='question_details'").fetchone():
                    columns={r['name'] for r in c.execute('PRAGMA table_info(question_details)')}-{'question_id'}
                    values={k:(json.dumps(normalized[k],ensure_ascii=False) if k in ('accepted_answers','solution_steps','rubric') and normalized.get(k) is not None else normalized[k]) for k in columns if k in normalized}
                    if values:c.execute('UPDATE question_details SET '+','.join(k+'=?' for k in values)+' WHERE question_id=?',(*values.values(),q['id']))
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='question_type_extensions'").fetchone():
                    old=c.execute('SELECT payload FROM question_type_extensions WHERE question_id=?',(q['id'],)).fetchone()
                    if old:
                        payload=json.loads(old[0]);payload.update({k:normalized[k] for k in payload if k in normalized})
                        c.execute('UPDATE question_type_extensions SET payload=? WHERE question_id=?',(json.dumps(payload,ensure_ascii=False),q['id']))
            c.execute('INSERT OR REPLACE INTO question_formula_status(question_id,formula_status,original_digest,canonical_digest,findings_json,normalizer_version) VALUES (?,?,?,?,?,?)',
                      (q['id'],status,row['original_digest'],digest(normalized) if status=='valid' else row['original_digest'],json.dumps(row['issues'],ensure_ascii=False),'V1.0D.4'))
        after=snapshot(c)
        if any(after[k]!=before[k] for k in before):raise ValueError('清洗改变了题量或历史作答，回滚')
        if c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('外键检查失败')
    profile_after=mastery_digest(path)
    if profile_before!=profile_after:raise AssertionError('修复前后掌握画像摘要不同')
    report={'backup':str(backup),'production':production,'snapshot_before':before,'snapshot_after':after,'attempts_unchanged':True,'mastery_digest_before':profile_before,'mastery_digest_after':profile_after,'mastery_unchanged':True,'status_counts':dict(Counter(r['formula_status'] for r in results))}
    print(json.dumps(report),flush=True);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',default=str(ROOT/'math_ai.db'));parser.add_argument('--apply',action='store_true');parser.add_argument('--allow-production',action='store_true');args=parser.parse_args()
    if args.apply:
        saved=json.loads((ROOT/'data/question_bank/formula_fixes/formula_audit_plan.json').read_text(encoding='utf-8'))
        result=apply(args.database,saved['questions'],allow_production=args.allow_production)
        if args.allow_production:(ROOT/'reports/v1_0d_4_production_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:plan(args.database)
