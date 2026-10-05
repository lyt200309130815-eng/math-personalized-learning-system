"""Conservative cross-batch duplicate identities without rewriting source text."""

import re
import unicodedata


def normalize_stem(stem: str) -> str:
    text = unicodedata.normalize("NFKC", stem)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^(?:(?:例|跟踪训练)\d+)?(?:\([12]\))|^(?:例|跟踪训练)\d+|^\d+[.、](?!\d)", "", text)
    text = re.sub(r"^\(\d{4}·[^)]*\)", "", text)
    return text


class DuplicateIndex:
    def __init__(self, questions=()):
        self.ids, self.fingerprints, self.stems, self.locators, self.source_numbers = set(), set(), set(), set(), set()
        for question in questions:
            self.add(question)

    @staticmethod
    def _source(question):
        return unicodedata.normalize("NFKC", question.get("source_file", "")).replace("\\", "/")

    def reasons(self, question: dict) -> list[str]:
        source = self._source(question)
        number = unicodedata.normalize("NFKC", str(question.get("source_question_number") or "")).strip()
        reasons = []
        for test, label in ((question.get("id") in self.ids, "id"),
                            (question.get("fingerprint") in self.fingerprints, "fingerprint"),
                            (normalize_stem(question["stem"]) in self.stems, "normalized_stem"),
                            ((source, question.get("source_locator")) in self.locators, "source_locator"),
                            (bool(number) and (source, number) in self.source_numbers, "source_question_number")):
            if test: reasons.append(label)
        return reasons

    def add(self, question: dict) -> None:
        source = self._source(question)
        self.ids.add(question.get("id"))
        self.fingerprints.add(question.get("fingerprint"))
        self.stems.add(normalize_stem(question["stem"]))
        self.locators.add((source, question.get("source_locator")))
        number = unicodedata.normalize("NFKC", str(question.get("source_question_number") or "")).strip()
        if number: self.source_numbers.add((source, number))


def quadratic_primary(stem: str) -> str | None:
    """Only explicit basic quadratic objectives qualify as K007, never quotas."""
    if not re.search(r"二次函数|抛物线|x\^\(2\)", stem): return None
    if re.search(r"最大值|最小值|最值|恒成立|恒非负", stem): return "K004"
    if re.search(r"单调|递增|递减", stem): return "K003"
    if re.search(r"值域|定义域", stem): return "K002"
    if re.search(r"顶点|对称轴|开口方向|开口向|基本性质", stem): return "K007"
    return None
