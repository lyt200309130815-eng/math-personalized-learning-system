"""V1.0B additive migration and training-session persistence."""
from contextlib import closing
import json
from pathlib import Path

from database.database import get_connection
from database.taxonomy_migration import protected_snapshot
from settings import get_database_path

MIGRATION_ID = 'v1_0b_training_sessions'
SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS schema_migrations (
        id TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
    '''CREATE TABLE IF NOT EXISTS training_sessions (
        id TEXT PRIMARY KEY, student_id TEXT NOT NULL, taxonomy_version TEXT NOT NULL,
        target_knowledge_point_id TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT, status TEXT NOT NULL DEFAULT 'active', initial_mastery REAL,
        final_mastery REAL, state_json TEXT NOT NULL,
        FOREIGN KEY(taxonomy_version,target_knowledge_point_id)
            REFERENCES knowledge_catalog(taxonomy_version,id))''',
    '''CREATE UNIQUE INDEX IF NOT EXISTS one_active_training
        ON training_sessions(student_id,taxonomy_version) WHERE status='active' ''',
    '''CREATE TABLE IF NOT EXISTS training_session_questions (
        session_id TEXT NOT NULL REFERENCES training_sessions(id),
        question_id TEXT NOT NULL REFERENCES questions(id), sequence_no INTEGER NOT NULL,
        difficulty INTEGER NOT NULL CHECK(difficulty BETWEEN 1 AND 5),
        selected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        attempt_id INTEGER UNIQUE REFERENCES attempts(id),
        attempt_mode TEXT NOT NULL DEFAULT 'training' CHECK(attempt_mode='training'),
        PRIMARY KEY(session_id,question_id), UNIQUE(session_id,sequence_no))''',
)


def migrate_training_sessions(database_path=None):
    """Idempotent transaction; no historical attempts or question bank changes."""
    path = Path(database_path or get_database_path())
    if not path.is_file():
        raise FileNotFoundError('待迁移数据库不存在。')
    with closing(get_connection(path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_catalog'").fetchone():
            raise ValueError('请先完成函数知识体系迁移。')
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
            if conn.execute('SELECT 1 FROM schema_migrations WHERE id=?', (MIGRATION_ID,)).fetchone():
                return {'applied': False, 'migration_id': MIGRATION_ID}
        before = protected_snapshot(conn)
        for sql in SCHEMA:
            conn.execute(sql)
        conn.execute('INSERT INTO schema_migrations(id) VALUES (?)', (MIGRATION_ID,))
        if protected_snapshot(conn) != before:
            raise ValueError('历史数据改变，训练 migration 回滚。')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('外键检查失败，训练 migration 回滚。')
    return {'applied': True, 'migration_id': MIGRATION_ID}


def load_session(conn, session_id, student_id=None):
    row = conn.execute('SELECT * FROM training_sessions WHERE id=?', (session_id,)).fetchone()
    if row is None or (student_id is not None and row['student_id'] != student_id):
        raise ValueError('训练不存在或不属于当前学生。')
    state = json.loads(row['state_json'])
    return state


def save_session(conn, state):
    conn.execute('''UPDATE training_sessions SET state_json=?, status=?, final_mastery=?,
        completed_at=CASE WHEN ?='active' THEN NULL ELSE COALESCE(completed_at,CURRENT_TIMESTAMP) END WHERE id=?''',
        (json.dumps(state, ensure_ascii=False), state['status'], state['final_mastery'], state['status'], state['id']))


def get_latest_session(student_id, database_path=None, *, taxonomy_version=None):
    from settings import get_active_taxonomy_version
    with closing(get_connection(database_path, read_only=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='training_sessions'").fetchone():
            return None
        row = conn.execute('''SELECT state_json FROM training_sessions WHERE student_id=?
            AND taxonomy_version=? ORDER BY rowid DESC LIMIT 1''', (student_id, taxonomy_version or get_active_taxonomy_version())).fetchone()
    return json.loads(row[0]) if row else None


def get_attempt_mode(attempt_id, database_path=None):
    """Preserve historical rows: linked diagnostic/training; unlinked is legacy."""
    with closing(get_connection(database_path, read_only=True)) as conn:
        for table, mode in (('training_attempt_links', 'training'), ('training_session_questions', 'training'), ('diagnostic_answers', 'diagnostic')):
            if conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                if conn.execute(f'SELECT 1 FROM {table} WHERE attempt_id=?', (attempt_id,)).fetchone():
                    return mode
    return 'legacy'
