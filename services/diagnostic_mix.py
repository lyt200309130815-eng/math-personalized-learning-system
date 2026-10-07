"""Small deterministic quota planner: coverage takes priority over type targets."""
from collections import Counter

TYPES = ('single_choice', 'multiple_choice', 'fill_blank', 'subjective')


def plan_questions(pool, count, recent_ids=(), previous_answers=()):
    """Assign one probe per point plus foundation follow-ups without ID bias.

    Dynamic programming searches attainable type counts across coverage slots.
    Only 18 slots and four types are involved; no optimization dependency is needed.
    """
    keys = sorted({q['knowledge_point_id'] for q in pool})
    covered = Counter(a['knowledge_point_id'] for a in previous_answers)
    slots = [k for k in keys if not covered[k]][:count]
    for key in ('K001', 'K002'):
        already = covered[key] + slots.count(key)
        if len(slots) < count and already < 2 and sum(q['knowledge_point_id'] == key for q in pool) > slots.count(key):
            slots.append(key)
    slots += [None] * (count-len(slots))
    total = count + len(previous_answers)
    previous_types = Counter(a.get('question_type','single_choice') for a in previous_answers)
    targets = [max(0, round(total*n/18)-previous_types[k]) for k,n in zip(TYPES,(6,2,7,3))]
    targets[0] += count-sum(targets)
    recent = set(recent_ids)
    states = {(0, 0, 0, 0): (0, [])}
    for key in slots:
        following = {}
        for counts, (cost, selected) in states.items():
            used = {q['id'] for q in selected}
            for index, kind in enumerate(TYPES):
                choices = [q for q in pool if q['id'] not in used
                           and (key is None or q['knowledge_point_id'] == key)
                           and q.get('question_type', 'single_choice') == kind]
                if not choices:
                    continue
                q = min(choices, key=lambda q: (q['id'] in recent, q['difficulty'], q['id']))
                updated = list(counts); updated[index] += 1; updated = tuple(updated)
                value = cost + (100 if q['id'] in recent else 0) + q['difficulty']
                if updated not in following or value < following[updated][0]:
                    following[updated] = (value, selected + [q])
        if not following:
            break
        states = following
    counts, (_, selected) = min(states.items(), key=lambda item: (
        sum(abs(a-b) for a,b in zip(item[0], targets)), item[1][0], item[0]))
    limitations = []
    if list(counts) != targets:
        limitations.append('知识点覆盖与现有题库限制使目标题型配额无法全部满足。')
    for key in keys:
        available = {q.get('question_type', 'single_choice') for q in pool if q['knowledge_point_id'] == key}
        missing = set(TYPES)-available
        if missing:
            limitations.append(f"{key}缺少诊断可用题型：{', '.join(sorted(missing))}。")
    return [q['id'] for q in selected], dict(zip(TYPES, counts)), limitations
