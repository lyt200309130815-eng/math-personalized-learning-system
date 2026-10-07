"""Explicit V1.0D.2 activation with SQLite backup, protected rows and idempotence."""
from contextlib import closing
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from database.database import get_connection, DATABASE_PATH, get_training_questions
from database.training_review import migrate_training_review
from services.question_importer import activate_training_questions
from services.question_validator import validate_candidate


def load_approved():
    rows=[]
    for kind in ('multiple_choice','fill_blank','subjective'):
        path=ROOT/f'data/question_bank/approved/function_{kind}_batch_001_approved.jsonl'
        rows.extend(json.loads(s) for s in path.read_text(encoding='utf-8').splitlines())
    for q in rows:
        # Historical user approval is immutable. Formula safety is a separate
        # trainability gate; legacy bad formulas are imported in quarantine.
        v=validate_candidate(q,check_formulas=False)
        if q['quality_status']!='approved' or not v['can_approve']:
            raise ValueError('批准题复检失败：'+q['id']+' '+str(v['errors']+v['warnings']))
    return rows


def snapshot(conn):
    attempts=[list(r) for r in conn.execute('SELECT * FROM attempts ORDER BY id')]
    return {'questions_count':conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0],
            'attempts_count':len(attempts),
            'attempts_digest':hashlib.sha256(json.dumps(attempts,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}


def integrate(path, *, allow_production=False):
    path=Path(path).resolve()
    if path==DATABASE_PATH.resolve() and not allow_production:raise ValueError('正式导入需要显式授权。')
    rows=load_approved()
    with closing(get_connection(path,read_only=True)) as original:
        before=snapshot(original)
        old_questions={r['id']:tuple(r) for r in original.execute('SELECT * FROM questions')}
        old_v1=get_training_questions(path,taxonomy_version='function_v1')
        backup_root=(ROOT/'backups') if path==DATABASE_PATH.resolve() else path.parent/'backups'
        backup_root.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup=backup_root/f'math_ai_before_v1_0d_2_{stamp}.sqlite3'
        with closing(get_connection(backup)) as target:original.backup(target)
    with closing(get_connection(backup,read_only=True)) as c:
        if snapshot(c)!=before:raise ValueError('备份与源快照不一致。')
    migration=migrate_training_review(path,allow_production=allow_production)
    imported=activate_training_questions(rows,database_path=path,allow_production=allow_production,quarantine_formulas=True)
    repeated=activate_training_questions(rows,database_path=path,allow_production=allow_production,quarantine_formulas=True)
    with closing(get_connection(path,read_only=True)) as c:
        after=snapshot(c)
        if before['attempts_count']!=after['attempts_count'] or before['attempts_digest']!=after['attempts_digest']:
            raise AssertionError('历史 attempts 校验不一致。')
        for row in c.execute('SELECT * FROM questions'):
            if row['id'] in old_questions and old_questions[row['id']]!=tuple(row):raise AssertionError('旧题被修改。')
        if c.execute('PRAGMA foreign_key_check').fetchall():raise AssertionError('外键不一致。')
        counts=dict(c.execute('SELECT question_type,COUNT(*) FROM questions GROUP BY question_type'))
        foreign_keys=c.execute('PRAGMA foreign_keys').fetchone()[0]
    if old_v1!=get_training_questions(path,taxonomy_version='function_v1'):raise AssertionError('function_v1 被改变。')
    if repeated['inserted']!=0:raise AssertionError('导入不幂等。')
    result={'stage':'V1.0D.2','database':str(path),'backup':str(backup),'before':before,'after':after,
            'approved_counts':{k:sum(q['question_type']==k for q in rows) for k in ('multiple_choice','fill_blank','subjective')},
            'migration':migration,'import':imported,'repeat_import':repeated,'question_type_counts':counts,
            'historical_attempts_unchanged':True,'all_original_questions_unchanged':True,
            'function_v1_unchanged':True,'foreign_keys':foreign_keys,'foreign_key_check':'passed'}
    if path==DATABASE_PATH.resolve():
        (ROOT/'reports/v1_0d_2_production_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',default=str(DATABASE_PATH));parser.add_argument('--apply-production',action='store_true')
    args=parser.parse_args()
    print(json.dumps(integrate(args.database,allow_production=args.apply_production),ensure_ascii=True,indent=2))
