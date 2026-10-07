"""Offline, restricted math parsing and deterministic objective evaluation.

No eval/parse_expr on student input. A small AST whitelist constructs SymPy
objects directly. Unsupported notation raises ValueError, never an LLM fallback.
"""
import ast
import re
import unicodedata

import sympy as sp

ANSWER_TYPES = {'numeric', 'expression', 'interval', 'set', 'text'}


class NeedsManualReview(ValueError):
    """Unsupported objective notation must never become an incorrect attempt."""
    status = 'needs_manual_review'


def parse_set(value):
    """Parse finite real sets, interval unions, R and the empty set only."""
    text = normalize_text(value)
    if text in ('∅', '{}', '空集'):
        return sp.S.EmptySet
    if text.startswith('{') and text.endswith('}'):
        parts = text[1:-1].split(',')
        if len(parts) > 30:
            raise ValueError('集合元素过多。')
        values = [parse_math(v) for v in parts]
        if any(v.free_symbols or v.is_real is not True or v.is_finite is not True for v in values):
            raise ValueError('仅支持有限实数集合。')
        return sp.FiniteSet(*values)
    return parse_interval(text)


def normalize_text(value: str) -> str:
    if not isinstance(value,str) or len(value)>500:
        raise ValueError('答案必须为不超过500字符的文本。')
    from services.math_normalizer import evaluator_math_text
    if '$' in value or '\\' in value:
        value = evaluator_math_text(value)
    return unicodedata.normalize('NFKC',value).strip().replace('−','-').replace('×','*').replace('·','*').replace('÷','/').replace('π','pi')


def parse_math(value: str, *, restrictions=None):
    text = normalize_text(value).replace('^','**')
    if not text or not re.fullmatch(r'[A-Za-z0-9+*/().\s-]+',text) or '__' in text:
        raise ValueError('不支持的数学表达式，请使用普通表达式，例如 (x-1)*(x+1)。')
    def scientific(match):
        if len(match[0])>30 or abs(int(re.split('[eE]',match[0])[1]))>100:
            raise ValueError('科学计数法超出基础判分范围。')
        return '('+str(sp.Rational(match[0]))+')'
    text=re.sub(r'\b(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+\b',scientific,text)
    # Only elementary implicit multiplication; function calls remain intact.
    text = re.sub(r'(?<=\d)(?=[A-Za-z(])|(?<=\))(?=[A-Za-z0-9(])','*',text)
    text = re.sub(r'\b([a-z])\s*(?=\()',r'\1*',text)
    try:
        tree = ast.parse(text,mode='eval')
    except (SyntaxError,RecursionError) as error:
        raise ValueError('表达式格式不支持。') from error
    if len(list(ast.walk(tree)))>100:
        raise ValueError('表达式过于复杂。')

    def bounded(item):
        if any(abs(int(n)).bit_length()>4096 for n in item.atoms(sp.Integer)):
            raise ValueError('数值超出基础判分范围。')
        for power in item.atoms(sp.Pow):
            if power.exp.is_number and abs(power.exp)>100:
                raise ValueError('幂次数超出基础判分范围。')
        return item

    def build(node,depth=0):
        if depth>20:
            raise ValueError('表达式嵌套过深。')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            literal = ast.get_source_segment(text,node)
            if len(literal)>30:
                raise ValueError('数值过大。')
            return sp.Rational(literal)
        if isinstance(node,ast.Name):
            if node.id == 'pi': return sp.pi
            if node.id in ('e','E'): return sp.E
            if node.id in ('oo','inf'): return sp.oo
            if len(node.id)==1 and node.id.isascii() and node.id.isalpha(): return sp.Symbol(node.id,real=True)
            raise ValueError('仅支持单字母变量和 pi、e。')
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            item = build(node.operand,depth+1)
            return item if isinstance(node.op,ast.UAdd) else -item
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            left,right = build(node.left,depth+1),build(node.right,depth+1)
            if isinstance(node.op,ast.Add): return bounded(left+right)
            if isinstance(node.op,ast.Sub): return bounded(left-right)
            if isinstance(node.op,ast.Mult): return bounded(left*right)
            if isinstance(node.op,ast.Div):
                if right==0: raise ValueError('不能除以零。')
                if restrictions is not None and right.free_symbols:
                    restrictions.append(('nonzero', right))
                return bounded(left/right)
            if right.free_symbols or right.is_real is not True or abs(right)>100:
                raise ValueError('指数超出基础判分范围。')
            if restrictions is not None and left.free_symbols:
                if right.is_integer and right < 0:
                    restrictions.append(('nonzero', left))
                elif right.is_integer is not True:
                    restrictions.append(('fractional_power', left, right))
            return bounded(left**right)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords and len(node.args)==1:
            functions = {'sqrt':sp.sqrt,'abs':sp.Abs,'ln':sp.log,'log':sp.log,'exp':sp.exp}
            if node.func.id in functions:
                item = build(node.args[0],depth+1)
                if restrictions is not None and item.free_symbols and node.func.id in ('sqrt','ln','log'):
                    restrictions.append(('nonnegative' if node.func.id=='sqrt' else 'positive', item))
                return functions[node.func.id](item)
        raise ValueError('表达式包含不允许的语法。')

    result = build(tree.body)
    if result.has(sp.zoo,sp.nan) or result.count_ops()>100:
        raise ValueError('表达式无效或过于复杂。')
    return result


def parse_interval(value):
    text = normalize_text(value).replace('∞','oo')
    if text in ('R','ℝ'): return sp.S.Reals
    pieces = re.split(r'∪|\bU\b',text)
    if len(pieces)>10: raise ValueError('区间数量过多。')
    intervals = []
    for part in pieces:
        part = part.strip()
        if len(part)<5 or part[0] not in '[(' or part[-1] not in '])':
            raise ValueError('请使用区间格式，例如 [0,1) 或 (-∞,0)∪(0,+∞)。')
        # Endpoints may themselves contain fractions and parentheses.
        inside = part[1:-1]
        if inside.count(',') != 1:
            raise ValueError('区间需要两个端点。')
        left,right = (parse_math(v) for v in inside.split(','))
        if left.free_symbols or right.free_symbols or left.is_extended_real is not True or right.is_extended_real is not True:
            raise ValueError('区间端点必须为实数。')
        if (left>right) is sp.S.true or left==sp.oo or right==-sp.oo:
            raise ValueError('区间端点顺序不合法。')
        if (left==-sp.oo and part[0]=='[') or (right==sp.oo and part[-1]==']'):
            raise ValueError('无穷端点必须为开端点。')
        intervals.append(sp.Interval(left,right,left_open=part[0]=='(',right_open=part[-1]==')'))
    return sp.Union(*intervals)


def evaluate_fill_blank(student_answer, expected_answer, answer_type):
    """Return bool for supported answers; malformed/unsupported input raises ValueError.

    Numeric comparison is exact, without an undocumented floating tolerance.
    Expression equivalence is algebraic; this foundation does not infer domains.
    """
    if answer_type not in ANSWER_TYPES:
        raise ValueError('不支持的填空答案类型。')
    if answer_type == 'text':
        return normalize_text(student_answer)==normalize_text(expected_answer)
    if answer_type == 'interval':
        return parse_interval(student_answer)==parse_interval(expected_answer)
    if answer_type == 'set':
        return parse_set(student_answer)==parse_set(expected_answer)
    left_domains=[];right_domains=[]
    left,right = parse_math(student_answer, restrictions=left_domains),parse_math(expected_answer, restrictions=right_domains)
    if answer_type == 'numeric' and any(v.free_symbols or v.is_real is not True or v.is_finite is not True for v in (left,right)):
        raise ValueError('请输入有限实数。')
    if any(v.has(sp.oo,-sp.oo) for v in (left,right)):
        raise ValueError('表达式不支持无穷值。')
    equivalent = sp.simplify(left-right)==0
    if equivalent and answer_type=='expression' and set(left_domains)!=set(right_domains):
        raise ValueError('表达式相同但定义域限制无法安全确认，需人工审核。')
    return equivalent


def evaluate_question(question, student_answer):
    """One scoring boundary shared by all training renderers."""
    kind = question.get('question_type','single_choice')
    if kind == 'subjective': return None
    if kind == 'single_choice':
        if student_answer not in ('A','B','C','D'): raise ValueError('请选择 A/B/C/D。')
        return student_answer==question['answer']
    if kind == 'multiple_choice':
        if isinstance(student_answer, str):
            try:
                import json
                selected = json.loads(student_answer) if student_answer.startswith('[') else list(student_answer)
            except ValueError as error:
                raise ValueError('多选答案格式不合法。') from error
        else:
            selected = student_answer
        if not isinstance(selected, (list, tuple, set)) or not selected or any(v not in question['options'] for v in selected):
            raise ValueError('请选择有效多选选项。')
        return set(selected) == set(question['correct_answers'])
    if kind != 'fill_blank': raise ValueError('不支持的题型。')
    expected = question.get('accepted_answers') or [question.get('canonical_answer') or question.get('answer_expression')]
    # Validate student syntax even if a later accepted answer is a match.
    try:
        return any(evaluate_fill_blank(student_answer,item,question['answer_type']) for item in expected)
    except ValueError as error:
        raise NeedsManualReview('needs_manual_review：答案无法安全解析，请核对格式或交由人工审核。') from error


def evaluate_answer_result(question, student_answer):
    """Structured result for callers that need an explicit review status."""
    try:
        correct = evaluate_question(question, student_answer)
        return {'status': 'pending' if correct is None else 'scored', 'is_correct': correct}
    except NeedsManualReview:
        return {'status': 'needs_manual_review', 'is_correct': None}
