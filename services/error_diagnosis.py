"""Deterministic suggestions and student-owned final classifications."""
ERROR_LABELS = dict(zip('KCLMRS', ['知识点不清楚','计算失误','推理过程不清楚','不会选择方法','看错题目','不知道从哪里开始']))


def suggest_error(hint_level=0, answer_time=0):
    if hint_level >= 2:
        return 'M', '已使用方法提示，建议回顾方法选择；也可以选择其他错因。'
    if answer_time < 5:
        return 'R', '作答较快，建议检查是否读清题意；这只是建议。'
    return 'K', '建议先检查定义与条件；仅凭选项不能确定真实错因。'
