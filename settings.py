"""Runtime configuration shared by database, services and UI."""
import os
from pathlib import Path

PRODUCTION_DATABASE_PATH = Path(__file__).resolve().parent / 'math_ai.db'


def get_active_taxonomy_version() -> str:
    version = os.environ.get('ACTIVE_TAXONOMY_VERSION', 'function_v1').strip() or 'function_v1'
    if version not in ('function_v1', 'function_v2'):
        raise ValueError('不支持的知识体系版本。')
    return version


def get_database_path() -> Path:
    return Path(os.environ.get('MATH_AI_DATABASE_PATH') or PRODUCTION_DATABASE_PATH).resolve()
