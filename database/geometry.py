"""Transactional, idempotent geometry import with backup and immutable attempts."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image

from database.database import DATABASE_PATH, get_connection
from database.taxonomy_migration import SCHEMA, validate_graph, protected_snapshot
from database.formula_status import store_status
from services.geometry_curation import KNOWLEDGE, PREREQUISITES, validate_geometry_question
from services.geometry_review import ROOT, file_hash
from services.math_normalizer import audit_question
from services.question_assets import geometry_trainable
from services.question_validator import content_fingerprint


def copy_assets(rows):
    for question in rows:
        for asset in question.get('diagram_assets', []):
            source = ROOT / 'data/question_bank/geometry_v1_1a' / asset['source_path']
            if file_hash(source) != asset['source_sha256']:
                raise ValueError('图形来源哈希改变')
            target = (ROOT / asset['path']).resolve()
            if (ROOT / 'data/question_assets/images/geometry').resolve() not in target.parents:
                raise ValueError('资产路径越界')
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                with Image.open(source) as image:
                    image.convert('RGBA').save(target, format='PNG')
            else:
                with Image.open(source) as original, Image.open(target) as existing:
                    if original.size != existing.size or original.convert('RGBA').tobytes() != existing.convert('RGBA').tobytes():
                        raise ValueError('稳定asset id对应的现有内容不一致')


def import_geometry(path, rows, *, allow_production=False, migration_id='v1_1c_geometry',
                    backup_prefix='math_ai_before_geometry_v1_1c_', review_records=None,
                    expected_baseline=None):
    path = Path(path).resolve()
    if path == DATABASE_PATH.resolve() and not allow_production:
        raise ValueError('正式几何导入需要显式生产授权')
    for row in rows:
        if not geometry_trainable(row, check_files=False) or row.get('issues') or row.get('warnings') or validate_geometry_question(row) or audit_question(row)['issues']:
            raise ValueError('生产门禁未通过：' + row['id'])
        if row['fingerprint'] != content_fingerprint(row):
            raise ValueError('生产题指纹不匹配：' + row['id'])
    points = [{'id': key, 'prerequisite_ids': PREREQUISITES[key]} for key in KNOWLEDGE]
    validate_graph(points)
    sha_before = file_hash(path)
    backup_dir = ROOT / 'backups' if path == DATABASE_PATH.resolve() else path.parent / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (backup_prefix + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
    with closing(get_connection(path, read_only=True)) as source, closing(get_connection(backup)) as target:
        before = protected_snapshot(source)
        source.backup(target)
    with closing(get_connection(backup, read_only=True)) as connection:
        backup_integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        if backup_integrity != 'ok':
            raise ValueError('SQLite backup integrity_check失败')
        if protected_snapshot(connection) != before:
            raise ValueError('SQLite backup与源数据库不一致')
    copy_assets(rows)
    inserted, skipped = 0, 0
    with closing(get_connection(path)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        locked_before = protected_snapshot(connection)
        if locked_before != before or (expected_baseline is not None and locked_before != expected_baseline):
            raise ValueError('数据库在审计/备份后发生变化，请重新读取当前基线；不回滚真实学生作答')
        if review_records is not None:
            from services.geometry_production_approval import duplicate_audit, load_geometry_rows
            collisions = duplicate_audit(rows, load_geometry_rows(connection), allow_identical=True)
            if any(r['duplicates'] and not r['already_integrated'] for r in collisions):
                raise ValueError('事务内重复检测发现变化，拒绝导入')
            connection.execute('''CREATE TABLE IF NOT EXISTS geometry_recovery_reviews(
                batch_id TEXT NOT NULL, question_id TEXT NOT NULL, review_status TEXT NOT NULL,
                reviewed_by TEXT NOT NULL, review_notes TEXT NOT NULL, gate_status TEXT NOT NULL,
                gate_reasons TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(batch_id,question_id))''')
            for record in review_records:
                connection.execute('INSERT INTO geometry_recovery_reviews VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                    ('geometry_recovery_batch_001',record['id'],record['review_status'],record['reviewed_by'],
                     record['review_notes'],record['production_gate_status'],json.dumps(record['production_gate_reasons'],ensure_ascii=False),
                     json.dumps(record,ensure_ascii=False,sort_keys=True)))
        for sql in SCHEMA:
            connection.execute(sql)
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='question_type_extensions'").fetchone():
            raise ValueError('请先完成现有四题型迁移；本导入不重建attempts')
        connection.execute("INSERT INTO taxonomy_versions(version,status) VALUES ('geometry_v1','active') ON CONFLICT(version) DO NOTHING")
        for order, (key, name) in enumerate(KNOWLEDGE.items(), 1):
            connection.execute('INSERT INTO knowledge_catalog VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                               ('geometry_v1', key, name, '立体几何与空间向量', '', order))
            connection.execute('INSERT INTO knowledge_points VALUES (?,?,?,NULL,?,?) ON CONFLICT DO NOTHING',
                               ('geometry_v1:' + key, name, '立体几何与空间向量', json.dumps(['geometry_v1:' + p for p in PREREQUISITES[key]]), ''))
            for parent in PREREQUISITES[key]:
                connection.execute('INSERT INTO knowledge_prerequisites VALUES (?,?,?) ON CONFLICT DO NOTHING', ('geometry_v1', key, parent))
        for question in rows:
            if not geometry_trainable(question):
                raise ValueError('正式图形文件无效：' + question['id'])
            existing = connection.execute('SELECT fingerprint FROM question_sources WHERE question_id=?', (question['id'],)).fetchone()
            if existing:
                if existing[0] != question['fingerprint']:
                    raise ValueError('相同题号内容不同，拒绝覆盖')
                skipped += 1
                continue
            if connection.execute("SELECT 1 FROM question_sources WHERE taxonomy_version='geometry_v1' AND fingerprint=?", (question['fingerprint'],)).fetchone():
                skipped += 1
                continue
            kind = question['question_type']
            connection.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (question['id'], question['stem'], json.dumps(question['options'], ensure_ascii=False) if question.get('options') else None,
                                question.get('answer') if kind == 'single_choice' else None, question['explanation'],
                                'geometry_v1:' + question['primary_knowledge_point_id'], question['difficulty'], '空间想象与推理', kind,
                                300 if kind == 'subjective' else 90))
            connection.execute('INSERT INTO question_details VALUES (?,?,?,?,?,?,?,?)',
                               (question['id'], question.get('canonical_answer'), json.dumps(question.get('accepted_answers'), ensure_ascii=False) if question.get('accepted_answers') else None,
                                question.get('answer_type'), question.get('reference_answer'), None, None, question.get('max_score')))
            # Explicit columns avoid assuming the historical details table layout.
            payload_keys = ['taxonomy_version', 'real_question', 'quality_status', 'formula_status', 'answer_leak_status', 'structure_status',
                            'primary_knowledge_point_id', 'related_knowledge_point_ids',
                            'trainable', 'diagram_required', 'diagram_assets', 'correct_answers', 'canonical_answer',
                            'sub_questions', 'judgment_answers', 'score_status', 'reviewed_by',
                            'review_status', 'review_notes', 'production_gate_status', 'source_fingerprint', 'variant_fingerprint']
            payload = {key: question[key] for key in payload_keys if key in question}
            connection.execute('INSERT INTO question_type_extensions VALUES (?,?)', (question['id'], json.dumps(payload, ensure_ascii=False)))
            for key, role in [(question['primary_knowledge_point_id'], 'primary')] + [(k, 'related') for k in question['related_knowledge_point_ids'] if k != question['primary_knowledge_point_id']]:
                connection.execute('INSERT INTO question_knowledge_mappings VALUES (?,?,?,?,?)', ('geometry_v1', question['id'], key, role, 'approved'))
            connection.execute('INSERT INTO question_sources VALUES (?,?,?,?,?,?,?,?,?)',
                               ('geometry_v1:' + question['id'], question['id'], 'geometry_v1', 'docx', question['source_file'],
                                question['source_locator'], '1', 'approved', question['fingerprint']))
            store_status(connection, question)
            inserted += 1
        after = protected_snapshot(connection)
        if before['rows']['attempts'] != after['rows']['attempts']:
            raise ValueError('历史attempts变化，回滚')
        old_questions = {row[0]: row for row in after['rows']['questions']}
        if any(old_questions.get(row[0]) != row for row in before['rows']['questions']):
            raise ValueError('旧题变化，回滚')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('外键校验失败，回滚')
        connection.execute("INSERT INTO taxonomy_migrations(migration_id,source_version,target_version,mapping_digest,status) VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                           (migration_id, 'local_docx', 'geometry_v1', hashlib.sha256(json.dumps([q['fingerprint'] for q in rows]).encode()).hexdigest(), 'applied'))
    return {'database': str(path), 'backup': str(backup), 'inserted': inserted, 'skipped': skipped,
            'before': {k: v for k, v in before.items() if k != 'rows'}, 'after': {k: v for k, v in after.items() if k != 'rows'},
            'sha256_before': sha_before, 'sha256_after': file_hash(path), 'attempts_unchanged': True, 'old_questions_unchanged': True,
            'backup_sha256': file_hash(backup), 'backup_integrity_check': backup_integrity}
