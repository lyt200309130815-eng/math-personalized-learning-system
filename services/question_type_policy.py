"""Transparent target ratios with deterministic deficit-based selection."""


def question_type_ratios(mastery_score):
    if mastery_score is None or mastery_score<.4:
        return {'single_choice':.50,'fill_blank':.40,'subjective':.10}
    if mastery_score<.7:
        return {'single_choice':.35,'fill_blank':.45,'subjective':.20}
    if mastery_score<.85:
        return {'single_choice':.25,'fill_blank':.45,'subjective':.30}
    return {'single_choice':.20,'fill_blank':.35,'subjective':.45}


def select_question_type(pool,answers,mastery_score):
    ratios = question_type_ratios(mastery_score)
    available = {q.get('question_type','single_choice') for q in pool}
    if 'multiple_choice' in available:
        choice_ratio = ratios['single_choice']
        ratios['multiple_choice'] = choice_ratio / 2 if 'single_choice' in available else choice_ratio
        ratios['single_choice'] -= ratios['multiple_choice']
    history = [a for a in answers if not a.get('is_retry',False)]
    total = len(history)+1
    counts = {kind:sum(a.get('question_type','single_choice')==kind for a in history) for kind in ratios}
    kinds = [kind for kind in ratios if kind in available and ratios[kind]>0]
    if not kinds: return None,ratios
    # A session is short: reserve an available blank by its sixth question,
    # and a comprehensive task for a proficient student before early completion.
    if total >= 5 and not counts['fill_blank'] and 'fill_blank' in kinds:
        return 'fill_blank',ratios
    if total >= 5 and mastery_score is not None and mastery_score >= .7 and not counts['subjective'] and 'subjective' in kinds:
        return 'subjective',ratios
    chosen = max(kinds,key=lambda kind:ratios[kind]*total-counts[kind])
    return chosen,ratios
