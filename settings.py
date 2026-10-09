"""Runtime configuration shared by database, services and UI."""
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

_DOTENV_INSERTED = {}

PROJECT_ROOT = Path(__file__).resolve().parent
PRODUCTION_DATABASE_PATH = PROJECT_ROOT / 'math_ai.db'


def load_local_environment(env_path: str | Path | None = None) -> bool:
    """Load the project .env silently; existing process variables always win.

    An explicit path supports isolated tests. Missing/unreadable files do not
    prevent non-AI learning features from starting. Never return secret values.
    """
    try:
        before = dict(os.environ)
        result = load_dotenv(dotenv_path=PROJECT_ROOT / '.env' if env_path is None else env_path,
                           override=False, encoding='utf-8-sig')
        _DOTENV_INSERTED.update({k: v for k, v in os.environ.items() if k not in before})
        return result
    except (OSError, UnicodeError):
        return False


# Resolve against this file, independent of a desktop shortcut's working folder.
load_local_environment()


def get_setting(name: str, default: str = "") -> str:
    """Resolve process environment, Streamlit secrets, local dotenv, then default."""
    value = os.environ.get(name)
    if value is not None and _DOTENV_INSERTED.get(name) != value:
        return value
    try:
        import streamlit as st
        secret = st.secrets.get(name)
        if secret is not None:
            return str(secret)
    except (FileNotFoundError, OSError):
        pass
    if value is not None:
        return value
    return default


def get_active_taxonomy_version() -> str:
    version = get_setting('ACTIVE_TAXONOMY_VERSION', 'function_v2').strip() or 'function_v2'
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx(suppress_warning=True) is not None:
        import streamlit as st
        version = st.session_state.get('active_taxonomy_version', version)
    if version not in ('function_v1', 'function_v2', 'geometry_v1'):
        raise ValueError('不支持的知识体系版本。')
    return version


def get_topic_name(version=None):
    return '立体几何与空间向量' if (version or get_active_taxonomy_version()) == 'geometry_v1' else '函数'


def get_database_path() -> Path:
    database_url = get_setting('DATABASE_URL')
    if database_url and not database_url.startswith('sqlite:///'):
        raise ValueError('本阶段仅支持 SQLite；PostgreSQL 适配尚未实现。')
    configured = database_url.removeprefix('sqlite:///') if database_url else get_setting('MATH_AI_DATABASE_PATH')
    path = Path(configured) if configured else PRODUCTION_DATABASE_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not configured and not path.exists():
        import shutil
        shutil.copyfile(PROJECT_ROOT / 'data/deployment/question_bank.db', path)
    return path.resolve()
