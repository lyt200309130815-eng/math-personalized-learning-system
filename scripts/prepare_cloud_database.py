"""Export only question-bank tables; never copy student records into deployment."""
import sqlite3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TABLES = {
    'knowledge_points', 'taxonomy_versions', 'knowledge_catalog',
    'knowledge_prerequisites', 'question_knowledge_mappings', 'question_tags',
    'question_prerequisites', 'question_sources', 'taxonomy_migrations',
    'schema_migrations', 'question_templates', 'question_resource_metadata',
    'questions', 'question_details', 'question_type_extensions', 'question_formula_status',
}

def export_database():
    source = ROOT / 'math_ai.db'
    target = ROOT / 'data/deployment/question_bank.db'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError('Deployment seed already exists; review before replacing it.')
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
        dst.execute('PRAGMA foreign_keys=OFF')
        tables = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for name in tables:
            if name not in TABLES:
                dst.execute('DELETE FROM "' + name + '"')
        dst.commit()
        dst.execute('VACUUM')
        if dst.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Seed foreign key check failed')
    print('Question-bank seed exported; student tables empty.')

if __name__ == '__main__':
    export_database()
