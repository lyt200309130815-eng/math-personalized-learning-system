"""Approved-only versioned bank import, isolated from the legacy training store."""

import json
import sqlite3
import os
from contextlib import closing
from pathlib import Path

from database.database import DATABASE_PATH, get_connection
from services.question_validator import load_taxonomy, validate_candidate


def import_questions(candidates: list[dict], *, database_path: str | Path) -> dict:
    """Import an approved batch atomically; reject real math_ai.db in V0.8B.

    This v2 bank has no route into legacy questions/attempts. Activating v2 training
    needs the separately reviewed taxonomy migration; never reinterpret old K005.
    """
    path = Path(database_path).resolve()
    if path == DATABASE_PATH.resolve() or (path.exists() and DATABASE_PATH.exists() and os.path.samefile(path, DATABASE_PATH)):
        raise ValueError("V0.8B 禁止导入真实 math_ai.db，请使用隔离数据库。")
    result = {"inserted": 0, "skipped": 0, "rejected": 0, "errors": []}
    accepted = []
    for candidate in candidates:
        validation = validate_candidate(candidate)
        if candidate.get("quality_status") != "approved" or not validation["can_approve"]:
            result["rejected"] += 1
            result["errors"].append({"id": candidate.get("id"), "reasons":
                                     validation["errors"] + validation["warnings"]
                                     + (["仅允许 approved"] if candidate.get("quality_status") != "approved" else [])})
        else:
            accepted.append(candidate)
    if not accepted:
        return result
    try:
        with closing(get_connection(path)) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("""CREATE TABLE IF NOT EXISTS bank_knowledge_points (
                    taxonomy_version TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
                    prerequisite_ids TEXT NOT NULL, PRIMARY KEY (taxonomy_version, id))""")
                connection.execute("""CREATE TABLE IF NOT EXISTS approved_question_bank (
                    id TEXT PRIMARY KEY, taxonomy_version TEXT NOT NULL,
                    primary_knowledge_point_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    quality_status TEXT NOT NULL CHECK (quality_status = 'approved'),
                    payload TEXT NOT NULL,
                    FOREIGN KEY (taxonomy_version, primary_knowledge_point_id)
                        REFERENCES bank_knowledge_points(taxonomy_version, id))""")
                taxonomy = load_taxonomy()
                connection.executemany("""INSERT INTO bank_knowledge_points VALUES (?, ?, ?, ?)
                                         ON CONFLICT(taxonomy_version, id) DO NOTHING""",
                                       [("function_v2", point["id"], point["name"], json.dumps(point["prerequisite_ids"]))
                                        for point in taxonomy["knowledge_points"]])
                for candidate in accepted:
                    same_id = connection.execute("SELECT fingerprint FROM approved_question_bank WHERE id = ?",
                                                 (candidate["id"],)).fetchone()
                    if same_id and same_id["fingerprint"] != candidate["fingerprint"]:
                        raise ValueError("相同题号对应不同内容，整批回滚")
                    exists = connection.execute("SELECT id FROM approved_question_bank WHERE fingerprint = ?",
                                                (candidate["fingerprint"],)).fetchone()
                    if exists:
                        result["skipped"] += 1
                        continue
                    connection.execute("""INSERT INTO approved_question_bank
                        (id, taxonomy_version, primary_knowledge_point_id, fingerprint, quality_status, payload)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                                       (candidate["id"], candidate["taxonomy_version"],
                                        candidate["primary_knowledge_point_id"], candidate["fingerprint"],
                                        "approved", json.dumps(candidate, ensure_ascii=False)))
                    result["inserted"] += 1
    except (sqlite3.Error, ValueError) as error:
        result["inserted"] = result["skipped"] = 0
        result["errors"].append({"id": None, "reasons": [f"整批回滚：{type(error).__name__}"]})
    return result


def get_approved_questions(knowledge_point_id: str, *, database_path: str | Path) -> list[dict]:
    """Read immutable approved source records, preserving their source fingerprints.

    Student training reads canonical, formula-gated questions through database.py.
    """
    with closing(get_connection(database_path, read_only=True)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  ("approved_question_bank",)).fetchone():
            return []
        rows = connection.execute("""SELECT payload FROM approved_question_bank
            WHERE taxonomy_version = ? AND primary_knowledge_point_id = ? AND quality_status = ?
            ORDER BY id""", ("function_v2", knowledge_point_id, "approved")).fetchall()
    from services.math_normalizer import audit_question
    result = []
    for row in rows:
        item = json.loads(row['payload'])
        if not audit_question(item)['issues']:
            result.append(item)
    return result


def activate_training_questions(candidates: list[dict], *, database_path: str | Path,
                                allow_production: bool = False, quarantine_formulas: bool = False) -> dict:
    """Explicit approved-only adapter into the migrated training store.

    Extracting/reviewing/importing candidates never calls this automatically.
    A production activation needs a caller's explicit authorization flag.
    """
    path = Path(database_path).resolve()
    is_production = path == DATABASE_PATH.resolve() or (path.exists() and DATABASE_PATH.exists() and os.path.samefile(path,DATABASE_PATH))
    if is_production and not allow_production:
        raise ValueError('真实数据库激活需要明确授权。')
    for q in candidates:
        validation = validate_candidate(q, check_formulas=not quarantine_formulas)
        if q.get('quality_status')!='approved' or not validation['can_approve']:
            raise ValueError('只有人工批准且通过分类校验的题才能进入训练。')
    from database.multi_type import migrate_multi_type, insert_question_details
    from database.taxonomy_migration import _insert_mapping
    migrate_multi_type(path)
    expanded = any(q.get('question_type') == 'multiple_choice' or q.get('answer_type') == 'set'
                   or any(k in q for k in ('canonical_answer', 'sub_questions')) for q in candidates)
    if expanded:
        from database.four_type import migrate_four_type
        migrate_four_type(path, allow_production=allow_production)
    inserted,skipped = 0,0
    with closing(get_connection(path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        historical_attempts=[tuple(r) for r in conn.execute('SELECT * FROM attempts ORDER BY id')]
        for q in candidates:
            from services.math_normalizer import audit_question
            from database.formula_status import store_status
            formula=audit_question(q)
            q=formula['normalized'] if not formula['issues'] else q
            existing = conn.execute('SELECT fingerprint FROM question_sources WHERE question_id=?',(q['id'],)).fetchone()
            if existing:
                if existing[0]!=q['fingerprint']: raise ValueError('相同题号对应不同内容。')
                skipped+=1
                continue
            if conn.execute("SELECT 1 FROM question_sources WHERE taxonomy_version='function_v2' AND fingerprint=?",(q['fingerprint'],)).fetchone():
                skipped+=1
                continue
            kind = q.get('question_type','single_choice')
            conn.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (q['id'],q['stem'],json.dumps(q['options'],ensure_ascii=False) if kind in ('single_choice','multiple_choice') else None,
                          q.get('answer') if kind=='single_choice' else None,q['explanation'],
                          'function_v2:'+q['primary_knowledge_point_id'],q['difficulty'],q['ability_tags'][0],kind,q['estimated_time']))
            insert_question_details(conn,q)
            if expanded:
                from database.four_type import insert_extensions
                insert_extensions(conn, q)
            _insert_mapping(conn,q['id'],q['primary_knowledge_point_id'],q['related_knowledge_point_ids'],
                            q['question_prerequisite_ids'],q['ability_tags'],q['method_tags'])
            conn.execute('INSERT INTO question_sources VALUES (?,?,?,?,?,?,?,?,?)',
                         ('function_v2:'+q['id'],q['id'],'function_v2',q['source_type'],q['source_file'],q['source_locator'],
                          str(q['version']),'approved',q['fingerprint']))
            store_status(conn,q)
            inserted+=1
        if historical_attempts != [tuple(r) for r in conn.execute('SELECT * FROM attempts ORDER BY id')]:
            raise ValueError('导入改变历史作答，整批回滚。')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('导入外键校验失败，整批回滚。')
    return {'inserted':inserted,'skipped':skipped}
