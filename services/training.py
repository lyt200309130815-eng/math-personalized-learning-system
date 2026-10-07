"""Session-based training timing and single-submission recording."""

from collections.abc import Callable, MutableMapping
from time import monotonic

from database.database import record_attempt


STUDENT_ID = "S001"


def initialize_training_state(state: MutableMapping, *, now: float | None = None) -> None:
    """Initialize once; ordinary reruns must not restart the question timer."""
    defaults = {"question_index": 0, "selected_answer": None, "submitted": False,
                "feedback": None, "recorded_attempt_id": None, "answer_time": None}
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
    if "question_started_at" not in state:
        state["question_started_at"] = monotonic() if now is None else now


def submit_training_answer(
    state: MutableMapping, question_id: str, correct_answer: str, *,
    now: float | None = None, recorder: Callable | None = None,
) -> None:
    """Record only from the submit callback and mark success immediately."""
    if state["submitted"] or state["recorded_attempt_id"] is not None:
        return
    selected = state["selected_answer"]
    if selected is None:
        state["feedback"] = "请选择一个答案后再提交。"
        return
    # Freeze the first valid submission time even if persistence fails.
    if state["answer_time"] is None:
        current_time = monotonic() if now is None else now
        state["answer_time"] = max(0.0, current_time - state["question_started_at"])
    is_correct = int(selected == correct_answer)
    attempt_id = (record_attempt if recorder is None else recorder)(
        student_id=state.get('student_id', STUDENT_ID), question_id=question_id, user_answer=selected,
        is_correct=is_correct, answer_time=state["answer_time"],
        hint_count=0, retry_count=0, error_type=None,
    )
    state["recorded_attempt_id"] = attempt_id
    state["submitted"] = True
    state["feedback"] = "回答正确" if is_correct else "回答错误"


def advance_question(state: MutableMapping, question_count: int, *, now: float | None = None) -> None:
    """Reset only on explicit navigation; allow another attempt on the new question."""
    state["question_index"] = (state["question_index"] + 1) % question_count
    state["selected_answer"] = None
    state["submitted"] = False
    state["feedback"] = None
    state["recorded_attempt_id"] = None
    state["answer_time"] = None
    state["question_started_at"] = monotonic() if now is None else now
