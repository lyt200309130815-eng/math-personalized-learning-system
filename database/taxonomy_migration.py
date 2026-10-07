"""Shared transactional V2 migration; production requires explicit authorization."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path

from database.database import DATABASE_PATH, get_connection
from services.question_validator import load_taxonomy, validate_candidate, content_fingerprint

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS taxonomy_versions(version TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK(status IN ('draft','active','retired')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS knowledge_catalog(taxonomy_version TEXT NOT NULL REFERENCES taxonomy_versions(version),
        id TEXT NOT NULL, name TEXT NOT NULL, topic TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        display_order INTEGER NOT NULL, PRIMARY KEY(taxonomy_version,id))""",
    """CREATE TABLE IF NOT EXISTS knowledge_prerequisites(taxonomy_version TEXT NOT NULL,
        knowledge_point_id TEXT NOT NULL, prerequisite_id TEXT NOT NULL,
        PRIMARY KEY(taxonomy_version,knowledge_point_id,prerequisite_id), CHECK(knowledge_point_id!=prerequisite_id),
        FOREIGN KEY(taxonomy_version,knowledge_point_id) REFERENCES knowledge_catalog(taxonomy_version,id),
        FOREIGN KEY(taxonomy_version,prerequisite_id) REFERENCES knowledge_catalog(taxonomy_version,id))""",
    """CREATE TABLE IF NOT EXISTS question_knowledge_mappings(taxonomy_version TEXT NOT NULL,
        question_id TEXT NOT NULL REFERENCES questions(id), knowledge_point_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('primary','related')),
        review_status TEXT NOT NULL CHECK(review_status IN ('approved','reviewed','draft','rejected')),
        PRIMARY KEY(taxonomy_version,question_id,knowledge_point_id,role),
        FOREIGN KEY(taxonomy_version,knowledge_point_id) REFERENCES knowledge_catalog(taxonomy_version,id))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS one_primary_per_question ON question_knowledge_mappings(taxonomy_version,question_id) WHERE role='primary'""",
    """CREATE TABLE IF NOT EXISTS question_tags(taxonomy_version TEXT NOT NULL, question_id TEXT NOT NULL REFERENCES questions(id),
        tag_type TEXT NOT NULL CHECK(tag_type IN ('ability','method')), tag TEXT NOT NULL,
        PRIMARY KEY(taxonomy_version,question_id,tag_type,tag), FOREIGN KEY(taxonomy_version) REFERENCES taxonomy_versions(version))""",
    """CREATE TABLE IF NOT EXISTS question_prerequisites(taxonomy_version TEXT NOT NULL,
        question_id TEXT NOT NULL REFERENCES questions(id), knowledge_point_id TEXT NOT NULL,
        PRIMARY KEY(taxonomy_version,question_id,knowledge_point_id),
        FOREIGN KEY(taxonomy_version,knowledge_point_id) REFERENCES knowledge_catalog(taxonomy_version,id))""",
    """CREATE TABLE IF NOT EXISTS question_sources(source_id TEXT PRIMARY KEY,
        question_id TEXT NOT NULL REFERENCES questions(id), taxonomy_version TEXT NOT NULL REFERENCES taxonomy_versions(version),
        source_type TEXT NOT NULL, source_file TEXT NOT NULL, locator TEXT NOT NULL,
        source_version TEXT, review_status TEXT NOT NULL, fingerprint TEXT NOT NULL,
        UNIQUE(taxonomy_version,fingerprint))""",
    """CREATE TABLE IF NOT EXISTS taxonomy_migrations(migration_id TEXT PRIMARY KEY,
        source_version TEXT NOT NULL, target_version TEXT NOT NULL, mapping_digest TEXT NOT NULL,
        status TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
)


def validate_graph(points):
    graph={p['id']:p['prerequisite_ids'] for p in points}
    if len(graph)!=len(points): raise ValueError('知识点ID重复。')
    visited=set()
    def visit(key, path=()):
        if key not in graph or key in path: raise ValueError('知识图引用无效或存在循环。')
        if key in visited: return
        for parent in graph[key]: visit(parent,path+(key,))
        visited.add(key)
    for key in graph: visit(key)


def require_isolated(path):
    path=Path(path).resolve()
    if path==DATABASE_PATH.resolve() or (path.exists() and DATABASE_PATH.exists() and os.path.samefile(path,DATABASE_PATH)):
        raise ValueError('V0.9A禁止迁移真实数据库。')
    return path


def protected_snapshot(connection):
    """Hash every field of historical rows in stable primary-key order."""
    rows = {table: [list(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY id')]
            for table in ('knowledge_points', 'questions', 'attempts')}
    attempts = rows['attempts']
    return dict(rows=rows, questions_count=len(rows['questions']), attempts_count=len(attempts),
                attempts_digest=hashlib.sha256(json.dumps(attempts, ensure_ascii=False, sort_keys=True).encode()).hexdigest())


def verify_migration(connection, before, approved):
    """Fail inside the transaction so any data or schema damage rolls back."""
    after = protected_snapshot(connection)
    if before['rows']['attempts'] != after['rows']['attempts']:
        raise ValueError('历史 attempts 改变，迁移回滚。')
    for table in ('knowledge_points', 'questions'):
        current = {row[0]: row for row in after['rows'][table]}
        if any(current.get(row[0]) != row for row in before['rows'][table]):
            raise ValueError(f'原有 {table} 行改变，迁移回滚。')
    points = [dict(id=r[0], prerequisite_ids=[p[0] for p in connection.execute(
        "SELECT prerequisite_id FROM knowledge_prerequisites WHERE taxonomy_version='function_v2' AND knowledge_point_id=?", (r[0],))])
        for r in connection.execute("SELECT id FROM knowledge_catalog WHERE taxonomy_version='function_v2'")]
    if {p['id'] for p in points} != {f'K{i:03d}' for i in range(1, 16)}:
        raise ValueError('V2知识点不完整。')
    validate_graph(points)
    expected = {q['id'] for q in approved} | {f'Q00{i}' for i in range(1, 7)}
    actual = connection.execute("SELECT question_id,COUNT(*) FROM question_knowledge_mappings WHERE taxonomy_version='function_v2' AND role='primary' AND review_status='approved' GROUP BY question_id").fetchall()
    if {r[0] for r in actual} != expected or any(r[1] != 1 for r in actual):
        raise ValueError('已批准主映射不完整或不唯一。')
    for question, primary in (('Q005', 'K003'), ('Q006', 'K004')):
        mapping = {(r[0], r[1]) for r in connection.execute("SELECT knowledge_point_id,role FROM question_knowledge_mappings WHERE taxonomy_version='function_v2' AND question_id=?", (question,))}
        if mapping != {(primary, 'primary'), ('K007', 'related')}:
            raise ValueError('旧参数题映射错误。')
    if connection.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('外键检查失败。')


def _activate(connection):
    connection.execute("UPDATE taxonomy_versions SET status='retired' WHERE version='function_v1' AND status!='retired'")
    connection.execute("UPDATE taxonomy_versions SET status='active' WHERE version='function_v2' AND status!='active'")


def migrate_function_v2(path, approved, *, allow_production=False):
    path=Path(path).resolve() if allow_production else require_isolated(path)
    if not path.is_file():
        raise FileNotFoundError('待迁移数据库不存在，拒绝创建空库。')
    taxonomy=load_taxonomy(); points=taxonomy['knowledge_points']; validate_graph(points)
    if len(points)!=15: raise ValueError('function_v2必须有15个节点。')
    if len({q['id'] for q in approved})!=len(approved) or len({q['fingerprint'] for q in approved})!=len(approved):
        raise ValueError('题号或指纹重复。')
    for q in approved:
        result=validate_candidate(q)
        if q['quality_status']!='approved' or not result['can_approve']:
            raise ValueError(f"{q['id']}未批准或校验失败：{result['errors']+result['warnings']}")
    mappings=next(s['question_mappings'] for s in taxonomy['sources'] if s['source_id']=='repository_seed_csv')
    digest=hashlib.sha256(json.dumps([taxonomy,approved,mappings],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with closing(get_connection(path)) as c:
        with c:
            c.execute('BEGIN IMMEDIATE')
            before = protected_snapshot(c)
            for sql in SCHEMA: c.execute(sql)
            old=c.execute('SELECT mapping_digest FROM taxonomy_migrations WHERE migration_id=?',('function_v2_initial',)).fetchone()
            if old:
                if old['mapping_digest']!=digest: raise ValueError('迁移清单摘要改变，拒绝覆盖。')
                if allow_production:
                    _activate(c)
                verify_migration(c, before, approved)
                return {'inserted':0,'skipped':len(approved)}
            c.executemany('INSERT INTO taxonomy_versions(version,status) VALUES (?,?)',[('function_v1','active'),('function_v2','draft')])
            legacy=c.execute("SELECT * FROM knowledge_points WHERE topic=? ORDER BY id",('函数',)).fetchall()
            for p in legacy:
                c.execute('INSERT INTO knowledge_catalog VALUES (?,?,?,?,?,?)',('function_v1',p['id'],p['name'],p['topic'],p['description'],len(p['id'])))
            for p in legacy:
                for parent in json.loads(p['prerequisite_ids']):
                    c.execute('INSERT INTO knowledge_prerequisites VALUES (?,?,?)',('function_v1',p['id'],parent))
            for order,p in enumerate(points):
                c.execute('INSERT INTO knowledge_catalog VALUES (?,?,?,?,?,?)',('function_v2',p['id'],p['name'],'函数','',order))
                # Namespaced FK bridge for unchanged legacy questions schema.
                # This is not a second graph; versioned relationship tables are authoritative.
                c.execute('INSERT INTO knowledge_points VALUES (?,?,?,?,?,?)',('function_v2:'+p['id'],p['name'],'function_v2',None,'[]','新题外键兼容节点，不用于旧体系。'))
            for p in points:
                for parent in p['prerequisite_ids']: c.execute('INSERT INTO knowledge_prerequisites VALUES (?,?,?)',('function_v2',p['id'],parent))
            old_questions=c.execute('SELECT * FROM questions ORDER BY id').fetchall()
            for q in old_questions:
                c.execute('INSERT INTO question_knowledge_mappings VALUES (?,?,?,?,?)',('function_v1',q['id'],q['knowledge_point_id'],'primary','approved'))
            for mapping in mappings:
                if not any(q['id']==mapping['question_id'] for q in old_questions): raise ValueError('缺少待映射旧题。')
                _insert_mapping(c,mapping['question_id'],mapping['primary_knowledge_point_id'],mapping['related_knowledge_point_ids'],
                                mapping['additional_prerequisite_ids'],mapping['ability_tags'],mapping['method_tags'])
            for q in approved:
                if c.execute('SELECT 1 FROM questions WHERE id=?',(q['id'],)).fetchone(): raise ValueError('新题ID与原库冲突。')
                c.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (q['id'],q['stem'],json.dumps(q['options'],ensure_ascii=False),q['answer'],q['explanation'],
                     'function_v2:'+q['primary_knowledge_point_id'],q['difficulty'],q['ability_tags'][0],'single_choice',q['estimated_time']))
                _insert_mapping(c,q['id'],q['primary_knowledge_point_id'],q['related_knowledge_point_ids'],q['question_prerequisite_ids'],q['ability_tags'],q['method_tags'])
                c.execute('INSERT INTO question_sources VALUES (?,?,?,?,?,?,?,?,?)',
                          ('function_v2:'+q['id'],q['id'],'function_v2',q['source_type'],q['source_file'],q['source_locator'],
                           q.get('source_ref',str(q['version'])),'approved',q['fingerprint']))
            c.execute('INSERT INTO taxonomy_migrations(migration_id,source_version,target_version,mapping_digest,status) VALUES (?,?,?,?,?)',
                      ('function_v2_initial','function_v1','function_v2',digest,'applied'))
            if allow_production:
                _activate(c)
            verify_migration(c, before, approved)
    return {'inserted':len(approved),'skipped':0}


def _insert_mapping(c,question,primary,related,prerequisites,abilities,methods):
    c.executemany('INSERT INTO question_knowledge_mappings VALUES (?,?,?,?,?)',
                  [('function_v2',question,primary,'primary','approved')]+[('function_v2',question,k,'related','approved') for k in related])
    c.executemany('INSERT INTO question_prerequisites VALUES (?,?,?)',[('function_v2',question,k) for k in prerequisites])
    c.executemany('INSERT INTO question_tags VALUES (?,?,?,?)',
                  [('function_v2',question,kind,tag) for kind,tags in (('ability',abilities),('method',methods)) for tag in tags])
