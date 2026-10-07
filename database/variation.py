"""Additive V1.0C schema; existing questions and attempts remain untouched."""
from contextlib import closing
import json

from database.database import get_connection
from database.training_sessions import migrate_training_sessions


def migrate_variation(database_path=None):
    migrate_training_sessions(database_path)
    from services.question_variation import TEMPLATES
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS question_templates (
            template_id TEXT PRIMARY KEY, knowledge_point_id TEXT NOT NULL,
            difficulty INTEGER NOT NULL CHECK(difficulty BETWEEN 1 AND 5),
            parameter_schema TEXT NOT NULL, generator_name TEXT NOT NULL,
            validator_name TEXT NOT NULL, quality_status TEXT NOT NULL
                CHECK(quality_status IN ('draft','reviewed','approved','rejected')),
            version TEXT NOT NULL, taxonomy_version TEXT NOT NULL DEFAULT 'function_v2',
            FOREIGN KEY(taxonomy_version,knowledge_point_id)
                REFERENCES knowledge_catalog(taxonomy_version,id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS question_variants (
            question_id TEXT PRIMARY KEY REFERENCES questions(id),
            template_id TEXT NOT NULL REFERENCES question_templates(template_id),
            parameter_set TEXT NOT NULL, generator_version TEXT NOT NULL,
            variant_fingerprint TEXT NOT NULL UNIQUE, hints_json TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK(source_type='generated_template'),
            source_url TEXT, license TEXT, usage_note TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS training_hint_events (
            id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES training_sessions(id),
            question_id TEXT NOT NULL REFERENCES questions(id),
            hint_level INTEGER NOT NULL CHECK(hint_level BETWEEN 1 AND 4),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS training_attempt_links (
            attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id),
            session_id TEXT NOT NULL REFERENCES training_sessions(id),
            question_id TEXT NOT NULL REFERENCES questions(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS question_resource_metadata (
            question_id TEXT PRIMARY KEY REFERENCES questions(id),
            source_url TEXT, license TEXT, usage_note TEXT)''')
        for template_id, spec in TEMPLATES.items():
            conn.execute('''INSERT OR IGNORE INTO question_templates
                (template_id,knowledge_point_id,difficulty,parameter_schema,generator_name,
                 validator_name,quality_status,version) VALUES (?,?,?,?,?,?,?,?)''',
                         (template_id, spec['knowledge_point_id'], 1,
                          json.dumps(spec['parameters']), template_id, template_id + '_validator',
                          'approved', '1'))
        conn.execute("INSERT OR IGNORE INTO schema_migrations(id) VALUES ('v1_0c_variation')")
