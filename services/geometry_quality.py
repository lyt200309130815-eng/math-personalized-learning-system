"""Source identity and explainable geometry difficulty drafts, without DB writes."""
import hashlib
from pathlib import Path
import re


DIFFICULTY_STANDARD = {
    1: '直接定义、基本性质、单步识别',
    2: '常规计算或单个定理应用',
    3: '两个以上知识步骤、常规空间向量计算、一般证明',
    4: '综合空间角/距离、多步骤证明、参数或探索问题、复杂截面',
    5: '高综合、动态轨迹或探索性存在问题与多知识链综合',
}


def source_fingerprint(question):
    """Same original start position has the same identity across repaired versions."""
    locator = question.get('source_locator', '') or ''
    match = re.search(r'paragraphs\s+(\d+)[–-](\d+)', locator)
    start = question.get('start_paragraph') or (int(match[1]) if match else None)
    file = question.get('source_file')
    if not file or start is None:
        return question.get('source_fingerprint') or question.get('fingerprint')
    # Source location is stable across repaired text/content fingerprints. Use
    # the same file identity for DB rows (which lack package hashes) and drafts.
    identity = (Path(file).as_posix().casefold(), int(start))
    return hashlib.sha256(repr(identity).encode('utf-8')).hexdigest()


def geometry_identity_tokens(question):
    """Combine source position with identical content copied to another source."""
    from services.question_validator import content_fingerprint
    tokens = {('content_fingerprint', content_fingerprint(question))}
    source = source_fingerprint(question)
    if source:
        tokens.add(('source_fingerprint', source))
    return tokens


def classify_geometry_difficulty(question):
    """Draft from actual tasks and solution operations; teachers confirm each draft.

    Neither question type alone nor desired coverage counts determine the level.
    Evidence snippets are retained for a reviewer to accept or amend the suggestion.
    """
    task = question.get('stem', '') + '\n' + '\n'.join(s['stem'] for s in question.get('sub_questions', []))
    solution = question.get('explanation') or question.get('reference_answer') or ''
    rules = {
        'vector_calculation': r'法向量|数量积|空间直角坐标系|坐标系|方向向量',
        'angle': r'所成角|二面角|夹角|正弦值|余弦值',
        'distance': r'距离',
        'proof': r'证明|求证',
        'parameter_exploration': r'是否存在|存在.*(?:点|实数|位置)|取值范围|设.*(?:λ|\\lambda|参数)',
        'dynamic': r'轨迹|运动|动点|变化|移动',
        'section': r'截面|交线|截得|截出',
        'concept': r'定义|基本性质|下列.*(?:正确|错误)|命题|判断',
    }
    evidence = {key: re.findall(pattern, task if key != 'vector_calculation' else solution)
                for key, pattern in rules.items()}
    steps = len(re.findall(r'所以|因此|从而|可得|则有|解得|建立|设.*法向量|由.*得', solution))
    sub_count = len(question.get('sub_questions', [])) or len(re.findall(r'(?:^|\n)\s*\([1-9]\)', task))
    mathematical_goals = sum(bool(evidence[key]) for key in ('angle', 'distance', 'proof', 'parameter_exploration', 'dynamic', 'section'))
    if ((evidence['dynamic'] or evidence['parameter_exploration'])
            and steps >= 6 and mathematical_goals >= 3):
        level, basis = 5, '动态/存在探索与至少三类数学目标、至少六个源解答推理步骤'
    elif ((evidence['parameter_exploration'] and steps >= 3)
          or (evidence['vector_calculation'] and (evidence['angle'] or evidence['distance']) and steps >= 4)
          or (evidence['proof'] and steps >= 6 and sub_count >= 2)
          or (evidence['section'] and steps >= 4)):
        level, basis = 4, '参数探索或空间角/距离/证明/截面的多步骤综合'
    elif evidence['vector_calculation'] or evidence['proof'] or steps >= 2:
        level, basis = 3, '常规向量计算、一般证明或至少两个源解答推理步骤'
    elif evidence['concept'] and steps <= 1 and not any(evidence[key] for key in ('angle', 'distance', 'parameter_exploration', 'dynamic', 'section')):
        level, basis = 1, '直接概念或性质识别，源解答不超过一个推理步骤'
    else:
        level, basis = 2, '常规计算或单个定理应用；无高阶复杂度的充分证据'
    return {'suggested': level, 'status': 'pending_review', 'basis': basis,
            'standard': DIFFICULTY_STANDARD[level], 'source_step_count': steps,
            'subquestion_count': sub_count, 'evidence': {k: v for k, v in evidence.items() if v}}


def geometry_difficulty_range(mastery):
    score = mastery['mastery_score']
    count = mastery.get('source_evidence_count', mastery['attempt_count'])
    if score is None or score < .4 or count <= 2:
        return (1, 2)
    if score < .8:
        return (2, 3)
    if score < .9 or count < 6:
        return (3, 4)
    return (4, 5)
