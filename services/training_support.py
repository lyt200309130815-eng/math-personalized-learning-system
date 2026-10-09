"""Transactional hints, error selection and append-only retries for training."""
from contextlib import closing
import time

from database.database import get_connection
from database.training_sessions import load_session, save_session
from services.error_diagnosis import ERROR_LABELS


def get_hint(question, level):
    if type(level) is not int or level not in range(1,5):
        raise ValueError('提示级别必须为1–4。')
    if question.get('hints'):
        return question['hints'][level-1]
    methods = {
        'K001': ('检查自变量到函数值的对应关系。','函数要求每个自变量对应唯一函数值。','逐一检查给定条件是否保证存在且唯一的函数值。'),
        'K002': ('先检查表达式有意义的条件。','检查分母不为零、根号内非负和对数真数为正等限制。','分别列出本题实际出现的限制，再取交集并检查端点。'),
        'K007': ('关注二次函数的图象与结构。','可用配方法识别对称轴和顶点。','识别二次项系数与一次项系数，先求 -b/(2a)。'),
        'K003': ('先明确需要判断增减性的区间。','使用单调性定义，或结合已知基本函数图象判断。','在给定区间取 x₁<x₂，比较 f(x₁) 与 f(x₂)，注意不等号方向。'),
        'K004': ('检查定义域与可能取得最值的位置。','结合单调区间、端点及可能的顶点求最值。','先计算题目范围内的候选端点或顶点函数值，排除不在定义域中的点。'),
        'K005': ('关注定义域是否关于原点对称。','比较 f(-x)、f(x) 和 -f(x)。','先将表达式中的 x 替换为 -x，再整理符号。'),
        'K009': ('关注指数函数底数与 1 的关系。','区分底数大于 1 和介于 0 与 1 的情况。','明确底数范围，再结合函数值恒正及单调方向检查选项。'),
        'K010': ('先检查对数函数的底数与真数条件。','底数须为正且不等于 1，真数必须为正。','先写出真数大于 0 的条件，再结合底数判断单调方向。'),
    }
    general = ('先明确题目已知条件与所求目标。',
               '回顾“'+question.get('knowledge_point_name','函数')+'”的定义与适用条件。',
               '写出已知条件对应的等式或不等式，检查定义域与边界后逐项排除。')
    return question.get('explanation','请回顾定义与条件。') if level == 4 else methods.get(question['knowledge_point_id'],general)[level-1]


def request_hint(student_id, session_id, level, *, database_path=None):
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = load_session(conn, session_id, student_id)
        q = state['current_question']
        if not q or state['status'] not in ('active','needs_support','completed'):
            raise ValueError('当前没有可提示题目。')
        if state['taxonomy_version'] == 'geometry_v1' and level == 4 and not state['submitted']:
            raise ValueError('请先作答，再查看完整解析。')
        content = get_hint(q,level)
        conn.execute('INSERT INTO training_hint_events(session_id,question_id,hint_level) VALUES (?,?,?)',(session_id,q['id'],level))
        state['hint_count'] = state.get('hint_count',0)+1
        state['question_hint_count'] = state.get('question_hint_count',0)+1
        state['hint_level'] = max(state.get('hint_level',0),level)
        state['visible_hint'] = content
        state['visible_hint_level'] = level
        save_session(conn,state)
        return state


def select_error_type(student_id,session_id,error_type,*,database_path=None):
    if error_type not in ERROR_LABELS:
        raise ValueError('错误类型必须为 K/C/L/M/R/S。')
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = load_session(conn,session_id,student_id)
        if not state['submitted'] or not state['answers'] or state['answers'][-1]['is_correct'] != 0:
            raise ValueError('只能为当前错误作答选择错因。')
        attempt = state['answers'][-1]
        conn.execute('UPDATE attempts SET error_type=? WHERE id=?',(error_type,attempt['attempt_id']))
        attempt['error_type'] = error_type
        save_session(conn,state)
        return state


def retry_question(student_id,session_id,*,database_path=None):
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        state = load_session(conn,session_id,student_id)
        if state.get('retry_pending'):
            return state
        if not state['submitted'] or not state['answers'] or state['answers'][-1]['is_correct'] != 0 or state['status'] not in ('active','completed','needs_support'):
            raise ValueError('当前题不允许重试。')
        state['retry_resume_status'] = state['status']
        state.update(status='active',submitted=False,retry_pending=True,question_started_at=time.time())
        state['retry_count'] = state.get('retry_count',0)+1
        state['question_retry_count'] = state.get('question_retry_count',0)+1
        save_session(conn,state)
        return state
