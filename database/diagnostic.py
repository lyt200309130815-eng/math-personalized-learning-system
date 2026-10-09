"""Additive assessment storage; attempts remain in their original schema."""
from contextlib import closing
import json
from pathlib import Path

from database.database import get_connection
from settings import get_database_path, get_active_taxonomy_version


def ensure_schema(database_path=None):
    """Create only V1.0A side tables, never migrate taxonomy or old attempts."""
    path = Path(database_path or get_database_path()).resolve()
    with closing(get_connection(path)) as conn, conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_catalog'").fetchone():
            raise ValueError('请先完成 function_v2 数据库迁移。')
        conn.execute('''CREATE TABLE IF NOT EXISTS diagnostic_sessions (
            id TEXT PRIMARY KEY, student_id TEXT NOT NULL, taxonomy_version TEXT NOT NULL,
            state_json TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS diagnostic_answers (
            session_id TEXT NOT NULL REFERENCES diagnostic_sessions(id),
            question_id TEXT NOT NULL REFERENCES questions(id),
            attempt_id INTEGER NOT NULL UNIQUE REFERENCES attempts(id),
            attempt_mode TEXT NOT NULL DEFAULT 'diagnostic' CHECK(attempt_mode='diagnostic'),
            PRIMARY KEY(session_id, question_id))''')
        conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS one_active_diagnostic
            ON diagnostic_sessions(student_id, taxonomy_version) WHERE completed=0''')


def load_latest(student_id, database_path=None, *, taxonomy_version=None):
    """Reading the landing page must not create tables or write records."""
    with closing(get_connection(database_path, read_only=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='diagnostic_sessions'").fetchone():
            return None
        row = conn.execute('''SELECT state_json FROM diagnostic_sessions
            WHERE student_id=? AND taxonomy_version=?
            ORDER BY rowid DESC LIMIT 1''', (student_id, taxonomy_version or get_active_taxonomy_version())).fetchone()
    return json.loads(row[0]) if row else None


def save_state(conn, state):
    conn.execute('''UPDATE diagnostic_sessions SET state_json=?, completed=? WHERE id=?''',
                 (json.dumps(state, ensure_ascii=False), int(state['diagnostic_completed']), state['id']))
