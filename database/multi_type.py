"""Transactional, idempotent multi-type migration preserving historical row values."""
from contextlib import closing
import json

from database.database import get_connection
from database.variation import migrate_variation

MIGRATION_ID = 'v1_0d_multi_type'

QUESTIONS_SQL = '''CREATE TABLE questions_v1_0d (
    id TEXT PRIMARY KEY NOT NULL, stem TEXT NOT NULL, options TEXT, answer TEXT,
    explanation TEXT NOT NULL, knowledge_point_id TEXT NOT NULL REFERENCES knowledge_points(id),
    difficulty INTEGER NOT NULL CHECK(difficulty BETWEEN 1 AND 5), ability_tag TEXT NOT NULL,
    question_type TEXT NOT NULL DEFAULT 'single_choice'
        CHECK(question_type IN ('single_choice','fill_blank','subjective')),
    estimated_time INTEGER NOT NULL CHECK(estimated_time>0),
    CHECK(question_type!='single_choice' OR (options IS NOT NULL AND answer IS NOT NULL AND answer IN ('A','B','C','D'))),
    CHECK(question_type='single_choice' OR (options IS NULL AND answer IS NULL)))'''
ATTEMPTS_SQL = '''CREATE TABLE attempts_v1_0d (
    id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL CHECK(length(trim(student_id))>0),
    question_id TEXT NOT NULL REFERENCES questions(id), user_answer TEXT NOT NULL,
    is_correct INTEGER CHECK(is_correct IN (0,1)), answer_time REAL NOT NULL CHECK(answer_time>=0),
    hint_count INTEGER NOT NULL DEFAULT 0 CHECK(hint_count>=0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count>=0),
    error_type TEXT CHECK(error_type IN ('K','C','L','M','R','S')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))'''
SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS question_details (
        question_id TEXT PRIMARY KEY REFERENCES questions(id), answer_expression TEXT,
        accepted_answers TEXT CHECK(accepted_answers IS NULL OR json_valid(accepted_answers)),
        answer_type TEXT CHECK(answer_type IN ('numeric','expression','interval','text')),
        reference_answer TEXT, solution_steps TEXT CHECK(solution_steps IS NULL OR json_valid(solution_steps)),
        rubric TEXT CHECK(rubric IS NULL OR json_valid(rubric)), max_score REAL CHECK(max_score>0))''',
    '''CREATE TABLE IF NOT EXISTS attempt_details (
        attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id),
        question_type TEXT NOT NULL CHECK(question_type IN ('single_choice','fill_blank','subjective')),
        answer_payload TEXT NOT NULL CHECK(json_valid(answer_payload)), attachment_path TEXT,
        scoring_status TEXT NOT NULL CHECK(scoring_status IN ('pending','scored')),
        score REAL, max_score REAL)''',
)


def migrate_multi_type(database_path=None):
    migrate_variation(database_path)
    with closing(get_connection(database_path)) as conn:
        # SQLite table rebuild: FK checking is disabled before the transaction,
        # and rechecked before commit. No ALTER rename of the original parent.
        conn.execute('PRAGMA foreign_keys=OFF')
        try:
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute('SELECT 1 FROM schema_migrations WHERE id=?',(MIGRATION_ID,)).fetchone():
                    return {'applied':False,'migration_id':MIGRATION_ID}
                saved = {t:[tuple(r) for r in conn.execute('SELECT * FROM '+t+' ORDER BY id')] for t in ('questions','attempts')}
                objects = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name IN ('questions','attempts') AND type IN ('index','trigger') AND sql IS NOT NULL")]
                sequence = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='attempts'").fetchone()
                conn.execute(QUESTIONS_SQL)
                conn.execute(ATTEMPTS_SQL)
                for table in ('questions','attempts'):
                    conn.execute(f'INSERT INTO {table}_v1_0d SELECT * FROM {table}')
                    conn.execute(f'DROP TABLE {table}')
                    conn.execute(f'ALTER TABLE {table}_v1_0d RENAME TO {table}')
                if sequence:
                    conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='attempts'",(sequence[0],))
                for sql in objects: conn.execute(sql)
                for sql in SCHEMA: conn.execute(sql)
                for event in ('INSERT','UPDATE'):
                    conn.execute(f'''CREATE TRIGGER validate_attempt_{event.lower()} BEFORE {event} ON attempts
                        BEGIN
                        SELECT CASE WHEN (SELECT question_type FROM questions WHERE id=NEW.question_id)='single_choice'
                            AND NEW.user_answer NOT IN ('A','B','C','D') THEN RAISE(ABORT,'invalid choice') END;
                        SELECT CASE WHEN (SELECT question_type FROM questions WHERE id=NEW.question_id)!='subjective'
                            AND NEW.is_correct IS NULL THEN RAISE(ABORT,'objective scoring required') END;
                        END''')
                after = {t:[tuple(r) for r in conn.execute('SELECT * FROM '+t+' ORDER BY id')] for t in saved}
                if saved != after or conn.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('多题型迁移校验失败，已回滚。')
                conn.execute('INSERT INTO schema_migrations(id) VALUES (?)',(MIGRATION_ID,))
        finally:
            conn.execute('PRAGMA foreign_keys=ON')
    return {'applied':True,'migration_id':MIGRATION_ID}


def insert_question_details(conn, question):
    if question.get('question_type','single_choice')=='single_choice': return
    def dump(key):
        return json.dumps(question[key],ensure_ascii=False) if question.get(key) is not None else None
    conn.execute('INSERT INTO question_details VALUES (?,?,?,?,?,?,?,?)',
                 (question['id'],question.get('canonical_answer') or question.get('answer_expression'),dump('accepted_answers'),
                  question.get('answer_type'),question.get('reference_answer'),dump('solution_steps'),
                  dump('rubric'),question.get('max_score')))
