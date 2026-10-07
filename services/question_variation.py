"""Small deterministic template registry, exact arithmetic and independent validators."""
from fractions import Fraction
import hashlib
import json
import random

TEMPLATES = {
    'quadratic_axis': {'knowledge_point_id': 'K007', 'parameters': {'a': [-3,-2,-1,1,2,3], 'h': list(range(-5,6)), 'k': list(range(-5,6))}},
    'quadratic_vertex': {'knowledge_point_id': 'K007', 'parameters': {'a': [-3,-2,-1,1,2,3], 'h': list(range(-5,6)), 'k': list(range(-5,6))}},
    'exponential': {'knowledge_point_id': 'K009', 'parameters': {'base': [2,3,4,5]}},
    'domain': {'knowledge_point_id': 'K002', 'parameters': {'bound': list(range(-12,13))}},
    'parity': {'knowledge_point_id': 'K005', 'parameters': {'power': [1,2,3,4,5,6], 'a': [-3,-2,-1,1,2,3]}},
}


def fingerprint(template_id, parameters):
    """Parameter identity intentionally survives generator version changes."""
    return hashlib.sha256(json.dumps([template_id, parameters], sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def validate_parameters(template_id, parameters):
    schema = TEMPLATES[template_id]['parameters']
    if set(parameters) != set(schema) or any(type(parameters[k]) is not int or parameters[k] not in schema[k] for k in schema):
        raise ValueError('模板参数不合法。')


def expected_answer(template_id, p):
    """Compute from expanded coefficients / definitions, independently of options."""
    validate_parameters(template_id, p)
    if template_id.startswith('quadratic'):
        a, b, c = p['a'], -2*p['a']*p['h'], p['a']*p['h']**2+p['k']
        axis = Fraction(-b, 2*a)
        if template_id == 'quadratic_axis':
            return str(axis)
        return f"({axis}, {a*axis**2+b*axis+c})"
    if template_id == 'domain':
        return f"[{p['bound']}, +∞)"
    if template_id == 'exponential':
        return '在 R 上严格递增，值域为 (0, +∞)'
    return '偶函数' if p['power'] % 2 == 0 else '奇函数'


def generate_variant(template_id, *, seed=0, parameters=None):
    rng = random.Random(seed)
    spec = TEMPLATES[template_id]
    p = parameters if parameters is not None else {k:rng.choice(v) for k,v in spec['parameters'].items()}
    validate_parameters(template_id, p)
    if template_id.startswith('quadratic'):
        a,h,k = p['a'],p['h'],p['k']
        stem = f"二次函数 f(x)={a}x²+({-2*a*h})x+({a*h*h+k}) 的" + ('对称轴 x 等于？' if template_id.endswith('axis') else '顶点坐标是？')
        correct = str(h) if template_id.endswith('axis') else f'({h}, {k})'
        distractors = [str(h+i) for i in (1,2,-1)] if template_id.endswith('axis') else [f'({h+i}, {k-i})' for i in (1,2,-1)]
        hints = ['关注二次函数图象的对称中心位置。', '使用配方法或对称轴公式 x=-b/(2a)。', f'先识别 a={a}，b={-2*a*h}，再代入公式。']
        explanation = f'由 x=-b/(2a) 得 x={h}；代回函数得 f({h})={k}。'
    elif template_id == 'domain':
        stem = f"函数 f(x)=√(x-({p['bound']})) 的定义域是？"
        correct = f"[{p['bound']}, +∞)"
        distractors = [f"({p['bound']}, +∞)", f"(-∞, {p['bound']}]", 'R']
        hints = ['检查表达式是否对所有实数有意义。', '实数范围内，被开方数必须非负。', f"列出 x-({p['bound']})≥0，注意等号是否允许。"]
        explanation = f"x-({p['bound']})≥0，所以定义域为 {correct}。"
    elif template_id == 'exponential':
        stem = f"指数函数 f(x)={p['base']}^x 的性质是？"
        correct = '在 R 上严格递增，值域为 (0, +∞)'
        distractors = ['在 R 上严格递减，值域为 (0, +∞)', '在 R 上严格递增，值域为 R', '在 R 上严格递减，值域为 R']
        hints = ['观察底数与 1 的关系。', '底数大于 1 时指数函数递增，函数值恒正。', '结合 x=0 时的函数值与两端趋势判断值域。']
        explanation = f"底数 {p['base']}>1，函数在 R 上严格递增，值域为 (0,+∞)。"
    else:
        stem = f"函数 f(x)={p['a']}x^{p['power']}（x∈R）的奇偶性是？"
        correct = '偶函数' if p['power'] % 2 == 0 else '奇函数'
        distractors = [v for v in ['偶函数','奇函数','既奇又偶','非奇非偶'] if v != correct]
        hints = ['先确认定义域关于原点对称。', '计算 f(-x)，与 f(x) 和 -f(x) 比较。', f"(-x)^{p['power']} 的符号由指数的奇偶性决定。"]
        explanation = '定义域 R 关于原点对称；代入 -x 后由幂的奇偶性可得：' + correct + '。'
    values = [correct] + distractors
    rng.shuffle(values)
    q = dict(template_id=template_id, parameter_set=p, generator_version='1',
             variant_fingerprint=fingerprint(template_id,p), stem=stem,
             options=dict(zip('ABCD',values)), answer='ABCD'[values.index(correct)],
             explanation=explanation, hints=hints+[explanation], difficulty=1,
             knowledge_point_id=spec['knowledge_point_id'], source_type='generated_template')
    if not validate_variant(q):
        raise ValueError('变式答案验证失败。')
    return q


def validate_variant(q):
    try:
        expected = expected_answer(q['template_id'], q['parameter_set'])
        from services.math_normalizer import normalize_math_text
        values = {k:normalize_math_text(v) for k,v in q['options'].items()}
        expected = normalize_math_text(expected)
        return (set(q['options']) == set('ABCD') and len(set(q['options'].values())) == 4
                and values.get(q['answer']) == expected
                and list(values.values()).count(expected) == 1
                and q['variant_fingerprint'] == fingerprint(q['template_id'],q['parameter_set']))
    except (KeyError, ValueError, TypeError):
        return False


def create_runtime_question(conn, state):
    """Generate one unseen parameter combination only from approved templates."""
    recent = {r[0] for r in conn.execute('''SELECT v.variant_fingerprint FROM training_session_questions s
        JOIN training_sessions t ON t.id=s.session_id JOIN question_variants v ON v.question_id=s.question_id
        WHERE t.student_id=? ORDER BY s.selected_at DESC,s.rowid DESC LIMIT 30''', (state['student_id'],))}
    recent.update(r[0] for r in conn.execute('''SELECT v.variant_fingerprint FROM training_session_questions s
        JOIN question_variants v ON v.question_id=s.question_id WHERE s.session_id=?''',(state['id'],)))
    templates = conn.execute("SELECT * FROM question_templates WHERE knowledge_point_id=? AND quality_status='approved' ORDER BY template_id", (state['target_knowledge_point_id'],)).fetchall()
    for template in templates:
        if template['version'] != '1':
            continue
        for seed in range(500):
            q = generate_variant(template['template_id'], seed=seed)
            from services.math_normalizer import audit_question
            from database.formula_status import store_status
            q = audit_question(q)['normalized']
            if q['variant_fingerprint'] in recent:
                continue
            qid = 'VAR_' + q['variant_fingerprint']
            if conn.execute('SELECT 1 FROM questions WHERE id=?',(qid,)).fetchone():
                continue
            conn.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (qid,q['stem'],json.dumps(q['options'],ensure_ascii=False),q['answer'],q['explanation'],
                          'K002' if q['template_id']=='domain' else 'K001',1,'concept_understanding','single_choice',60))
            conn.execute("INSERT INTO question_knowledge_mappings VALUES ('function_v2',?,?,'primary','approved')",(qid,q['knowledge_point_id']))
            conn.execute('INSERT INTO question_variants VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (qid,q['template_id'],json.dumps(q['parameter_set'],sort_keys=True), '1',q['variant_fingerprint'],json.dumps(q['hints'],ensure_ascii=False),'generated_template',None,None,'本地确定性模板技术验证'))
            conn.execute("INSERT INTO question_sources VALUES (?,?,'function_v2','generated_template',?,?,?,'approved',?)",
                         (qid,qid,'services/question_variation.py',q['template_id'],'1',q['variant_fingerprint']))
            q['id'] = qid
            q['knowledge_point_name'] = state['target_name']
            store_status(conn,q)
            return q
    return None
