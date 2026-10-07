"""Formula audit side table, independent of student attempts and approval."""
import hashlib
import json
from services.math_normalizer import audit_question, FIELDS


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS question_formula_status (
        question_id TEXT PRIMARY KEY REFERENCES questions(id),formula_status TEXT NOT NULL
        CHECK(formula_status IN ('valid','formula_warning','formula_manual_review','invalid')),
        original_digest TEXT NOT NULL,canonical_digest TEXT NOT NULL,findings_json TEXT NOT NULL,
        normalizer_version TEXT NOT NULL,audited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def store_status(conn, question):
    ensure_schema(conn)
    checked=audit_question(question)
    encoded=json.dumps({k:question.get(k) for k in FIELDS},ensure_ascii=False,sort_keys=True).encode()
    digest=hashlib.sha256(encoded).hexdigest()
    conn.execute('INSERT OR REPLACE INTO question_formula_status(question_id,formula_status,original_digest,canonical_digest,findings_json,normalizer_version) VALUES (?,?,?,?,?,?)',
                 (question['id'],checked['formula_status'],digest,digest,json.dumps(checked['issues'],ensure_ascii=False),'V1.0D.4'))
