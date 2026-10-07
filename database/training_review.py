"""Append-only unscored submissions and compatible nullable objective evidence."""
from contextlib import closing

from database.database import get_connection
from database.four_type import migrate_four_type

MIGRATION_ID='v1_0d_2_training_review'


def migrate_training_review(database_path, *, allow_production=False):
    migrate_four_type(database_path,allow_production=allow_production)
    with closing(get_connection(database_path)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM schema_migrations WHERE id=?',(MIGRATION_ID,)).fetchone():
            return {'applied':False}
        # Pending fill answers use existing nullable attempts and pending details.
        # The explicit reason is stored separately, without altering historical rows.
        conn.execute('''CREATE TABLE answer_review_requests (
            attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id),
            status TEXT NOT NULL CHECK(status IN ('needs_manual_review','reviewed')),
            reason TEXT NOT NULL, requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE subjective_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL, question_id TEXT NOT NULL REFERENCES questions(id),
            attempt_id INTEGER NOT NULL UNIQUE REFERENCES attempts(id),
            text_answer TEXT NOT NULL, attachment_path TEXT,
            status TEXT NOT NULL CHECK(status IN ('submitted_pending_review','reviewed','needs_revision')),
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, score REAL,
            max_score REAL NOT NULL CHECK(max_score>0), review_source TEXT,
            CHECK(score IS NULL OR (score>=0 AND score<=max_score)))''')
        for event in ('INSERT','UPDATE'):
            conn.execute('DROP TRIGGER IF EXISTS validate_attempt_'+event.lower())
            conn.execute(f'''CREATE TRIGGER validate_attempt_{event.lower()} BEFORE {event} ON attempts
                BEGIN
                SELECT CASE WHEN (SELECT question_type FROM questions WHERE id=NEW.question_id)='single_choice'
                    AND NEW.user_answer NOT IN ('A','B','C','D') THEN RAISE(ABORT,'invalid choice') END;
                SELECT CASE WHEN (SELECT question_type FROM questions WHERE id=NEW.question_id) IN ('single_choice','multiple_choice')
                    AND NEW.is_correct IS NULL THEN RAISE(ABORT,'objective scoring required') END;
                END''')
        conn.execute('INSERT INTO schema_migrations(id) VALUES (?)',(MIGRATION_ID,))
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('待评阅迁移外键检查失败。')
    return {'applied':True}


def pending_counts(student_id, *, database_path=None, taxonomy_version='function_v2'):
    """Separate pending work from effective evidence; no scores are calculated."""
    with closing(get_connection(database_path,read_only=True)) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='attempt_details'").fetchone():return {}
        if taxonomy_version=='function_v2':
            query='''SELECT m.knowledge_point_id AS point,q.question_type,COUNT(*) AS count
                FROM attempts a JOIN questions q ON q.id=a.question_id
                JOIN attempt_details d ON d.attempt_id=a.id
                JOIN question_knowledge_mappings m ON m.question_id=q.id
                WHERE a.student_id=? AND d.scoring_status='pending'
                AND m.taxonomy_version='function_v2' AND m.role='primary' AND m.review_status='approved'
                GROUP BY point,q.question_type'''
        else:
            query='''SELECT q.knowledge_point_id AS point,q.question_type,COUNT(*) AS count
                FROM attempts a JOIN questions q ON q.id=a.question_id
                JOIN attempt_details d ON d.attempt_id=a.id WHERE a.student_id=?
                AND d.scoring_status='pending' GROUP BY point,q.question_type'''
        result={}
        for r in c.execute(query,(student_id,)):
            result.setdefault(r['point'],{'subjective':0,'fill_blank':0})[r['question_type']]=r['count']
        return result
