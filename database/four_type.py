"""Four-type schema upgrade; production requires explicit authorized integration."""
from contextlib import closing
import json

from database.database import get_connection
from database.multi_type import migrate_multi_type, QUESTIONS_SQL, SCHEMA
from database.taxonomy_migration import require_isolated

MIGRATION_ID = 'v1_0d_1_four_types'


def migrate_four_type(database_path, *, allow_production=False):
    from pathlib import Path
    path = Path(database_path).resolve() if allow_production else require_isolated(database_path)
    migrate_multi_type(path)
    with closing(get_connection(path)) as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        try:
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute('SELECT 1 FROM schema_migrations WHERE id=?', (MIGRATION_ID,)).fetchone():
                    return {'applied': False}
                saved = {t: [tuple(r) for r in conn.execute('SELECT * FROM '+t)]
                         for t in ('questions', 'question_details', 'attempt_details', 'attempts')}
                triggers = list(conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
                for trigger in triggers:
                    conn.execute('DROP TRIGGER "'+trigger['name'].replace('"','""')+'"')
                definitions = {
                    'questions': QUESTIONS_SQL.replace('questions_v1_0d', 'questions_four')
                        .replace("'single_choice','fill_blank'", "'single_choice','multiple_choice','fill_blank'")
                        .replace("question_type='single_choice' OR (options IS NULL AND answer IS NULL)",
                                 "question_type='single_choice' OR (question_type='multiple_choice' AND options IS NOT NULL AND answer IS NULL) OR (question_type IN ('fill_blank','subjective') AND options IS NULL AND answer IS NULL)"),
                    'question_details': SCHEMA[0].replace('CREATE TABLE IF NOT EXISTS question_details', 'CREATE TABLE question_details_four')
                        .replace("'interval','text'", "'interval','set','text'"),
                    'attempt_details': SCHEMA[1].replace('CREATE TABLE IF NOT EXISTS attempt_details', 'CREATE TABLE attempt_details_four')
                        .replace("'single_choice','fill_blank'", "'single_choice','multiple_choice','fill_blank'")}
                for table, sql in definitions.items():
                    objects = [r[0] for r in conn.execute(
                        "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL", (table,))]
                    conn.execute(sql)
                    target = 'questions_four' if table == 'questions' else table+'_four'
                    conn.execute(f'INSERT INTO {target} SELECT * FROM {table}')
                    conn.execute('DROP TABLE '+table)
                    conn.execute(f'ALTER TABLE {target} RENAME TO {table}')
                    for definition in objects: conn.execute(definition)
                for trigger in triggers: conn.execute(trigger['sql'])
                conn.execute('''CREATE TABLE question_type_extensions (
                    question_id TEXT PRIMARY KEY REFERENCES questions(id),
                    payload TEXT NOT NULL CHECK(json_valid(payload)))''')
                after = {t: [tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in saved}
                if saved != after or conn.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('四题型迁移校验失败。')
                conn.execute('INSERT INTO schema_migrations(id) VALUES (?)', (MIGRATION_ID,))
        finally:
            conn.execute('PRAGMA foreign_keys=ON')
    return {'applied': True}


def insert_extensions(conn, question):
    from services.question_structure import runtime_metadata
    payload = runtime_metadata(question)
    if payload:
        conn.execute('INSERT INTO question_type_extensions VALUES (?,?)',
                     (question['id'], json.dumps(payload, ensure_ascii=False)))
