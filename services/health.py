"""Read-only deployment checks without credentials or student information."""
from contextlib import closing
from database.database import get_connection, get_training_questions
from services.question_assets import readable_asset
from settings import get_setting


def get_health():
    result = {'database_readable': False, 'question_bank_readable': False,
              'function_v2': False, 'geometry_v1': False,
              'images_readable': False,
              'deepseek_configured': bool(get_setting('DEEPSEEK_API_KEY').strip())}
    try:
        with closing(get_connection(read_only=True)) as conn:
            conn.execute('SELECT 1 FROM questions LIMIT 1').fetchone()
        result['database_readable'] = True
        assets = []
        for version in ('function_v2', 'geometry_v1'):
            questions = get_training_questions(taxonomy_version=version)
            result[version] = bool(questions)
            assets.extend(a for q in questions for a in q.get('diagram_assets', []))
        result['question_bank_readable'] = result['function_v2'] and result['geometry_v1']
        result['images_readable'] = all(readable_asset(a) for a in assets)
    except Exception:
        pass  # Never expose configuration values or connection exceptions in the UI.
    return result
