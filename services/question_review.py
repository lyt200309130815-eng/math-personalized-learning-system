"""Immutable snapshots, resumable human review and derived gold exports."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from services.question_validator import load_taxonomy, validate_candidate

CHECKLIST = ("答案是否正确", "解析是否推出答案", "选项是否唯一", "是否存在定义域遗漏",
             "是否存在参数边界遗漏", "difficulty 是否合理", "primary 知识点是否正确")
REVIEW_FIELDS = {"quality_status", "annotation_status", "review_confirmation", "review_notes",
                 "reviewed_by", "reviewed_at", "review_decision", "candidate_snapshot_sha256"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_write(path: Path, text: str) -> None:
    """Journal is authoritative; interrupted derived exports can be regenerated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class ReviewSession:
    """Review events change audit metadata only, never source question content."""

    def __init__(self, snapshot: Path, reviews: Path, approved: Path, report: Path):
        self.snapshot = Path(snapshot).resolve()
        self.reviews, self.approved, self.report = map(Path, (reviews, approved, report))
        outputs = [path.resolve() for path in (self.reviews, self.approved, self.report)]
        if self.snapshot in outputs or len(set(outputs)) != 3:
            raise ValueError("审核输出不能覆盖候选快照，三个输出路径必须不同。")
        if any(path.exists() and os.path.samefile(path, self.snapshot)
               for path in (self.reviews, self.approved, self.report)):
            raise ValueError("审核输出不能指向候选快照的硬链接。")
        self.digest = hashlib.sha256(self.snapshot.read_bytes()).hexdigest()
        self.candidates = read_jsonl(self.snapshot)
        self.by_id = {row["id"]: row for row in self.candidates}
        if len(self.by_id) != len(self.candidates):
            duplicate = [key for key, count in Counter(row['id'] for row in self.candidates).items() if count > 1]
            raise ValueError("候选题 ID 重复：" + ", ".join(duplicate))
        if any(row.get("quality_status") != "reviewed" for row in self.candidates):
            raise ValueError("只允许审核 reviewed 候选快照。")
        self.events = read_jsonl(self.reviews) if self.reviews.exists() else []
        self.latest = {}
        for event in self.events:
            self._validate_event(event)
            self.latest[event["id"]] = event

    def _validate_event(self, event: dict) -> None:
        original = self.by_id.get(event.get("id"))
        if original is None or event.get("candidate_snapshot_sha256") != self.digest:
            raise ValueError("审核记录与候选快照不匹配。")
        for key in set(original) | set(event):
            if key not in REVIEW_FIELDS and original.get(key) != event.get(key):
                raise ValueError("审核记录改变了题目内容或来源。")
        statuses = {"approve": "approved", "reject": "rejected", "skip": "reviewed"}
        decision = event.get("review_decision")
        if (decision not in statuses or event.get("quality_status") != statuses[decision]
                or not isinstance(event.get("reviewed_by"), str) or not event["reviewed_by"].strip()
                or not isinstance(event.get("review_notes"), list)):
            raise ValueError("审核决定或审核人无效。")
        try:
            timestamp = datetime.fromisoformat(event["reviewed_at"].replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError("审核时间缺少时区")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("审核时间无效。") from error
        if decision == "approve" and not validate_candidate(event)["can_approve"]:
            raise ValueError("批准记录未通过二次校验。")
        if decision == "approve":
            confirmation = event["review_confirmation"]
            if confirmation.get("reviewer") != event["reviewed_by"] or confirmation.get("checklist") != list(CHECKLIST):
                raise ValueError("批准记录缺少一致的审核人或数学 checklist。")

    def pending(self, *, revisit_skipped: bool = False) -> list[dict]:
        return [row for row in self.candidates if row["id"] not in self.latest
                or (revisit_skipped and self.latest[row["id"]]["review_decision"] == "skip")]

    def decide(self, question_id: str, decision: str, reviewer: str, notes: str = "",
               *, confirmed: bool = False) -> dict:
        if decision not in {"approve", "reject", "skip"} or not reviewer.strip():
            raise ValueError("必须提供合法审核决定与审核人。")
        if hashlib.sha256(self.snapshot.read_bytes()).hexdigest() != self.digest:
            raise ValueError("候选快照在审核期间发生变化。")
        original = self.by_id[question_id]
        if decision == "approve" and (not confirmed or not validate_candidate(original)["can_approve"]):
            raise ValueError("批准需要数学确认，且完整性校验无错误、无 warning。")
        event = deepcopy(original)
        event.update(
            quality_status={"approve": "approved", "reject": "rejected", "skip": "reviewed"}[decision],
            reviewed_by=reviewer.strip(), reviewed_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            review_decision=decision, candidate_snapshot_sha256=self.digest,
            review_notes=list(original.get("review_notes", [])) + ([notes.strip()] if notes.strip() else []),
        )
        if decision == "approve":
            event["annotation_status"] = "confirmed"
            event["review_confirmation"] = {"reviewer": reviewer.strip(), "confirmed": True, "checklist": list(CHECKLIST)}
        self._validate_event(event)
        events = self.events + [event]
        atomic_write(self.reviews, self._jsonl(events))
        self.events = events
        self.latest[question_id] = event
        self.save_outputs()
        return event

    @staticmethod
    def _jsonl(rows: list[dict]) -> str:
        return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)

    def save_outputs(self) -> None:
        if hashlib.sha256(self.snapshot.read_bytes()).hexdigest() != self.digest:
            raise ValueError("候选快照在审核期间发生变化。")
        if not self.reviews.exists():
            atomic_write(self.reviews, "")
        approved = [self.latest[row["id"]] for row in self.candidates
                    if row["id"] in self.latest and self.latest[row["id"]]["quality_status"] == "approved"]
        for event in approved:
            self._validate_event(event)
        atomic_write(self.approved, self._jsonl(approved))
        atomic_write(self.report, self.build_report(approved))

    def build_report(self, approved: list[dict]) -> str:
        decisions = Counter(row["review_decision"] for row in self.latest.values())
        knowledge = Counter(row["primary_knowledge_point_id"] for row in approved)
        difficulty = Counter(row["difficulty"] for row in approved)
        ability = Counter(tag for row in approved for tag in row["ability_tags"])
        method = Counter(tag for row in approved for tag in row["method_tags"])
        taxonomy = load_taxonomy()
        lines = ["# 第一批金标准题人工审核报告", "", "## 审核进度", "",
                 f"候选总数：{len(self.candidates)}", f"approved：{decisions['approve']}", f"rejected：{decisions['reject']}",
                 f"skipped/reviewed：{len(self.candidates)-decisions['approve']-decisions['reject']}",
                 f"reviewed remaining：{len(self.candidates)-decisions['approve']-decisions['reject']}",
                 f"其中显式 skip：{decisions['skip']}；尚未审核：{len(self.candidates)-len(self.latest)}", "",
                 "尚未人工批准的题不会成为金标准题。跳过不代表拒绝或批准。",
                 "批准须核对答案、解析、选项唯一性、定义域、参数边界、难度及主要知识点。",
                 "严格策略：非 complete 或有 warning 不允许批准，本阶段不提供 warning 覆盖。",
                 "候选快照只读；审核日志为恢复依据，批准文件和本报告可重新生成。", "",
                 f"候选 SHA-256：`{self.digest}`", "", "## approved 知识点分布", "",
                 "| 知识点 | 数量 |", "| --- | ---: |"]
        lines += [f"| {p['id']} {p['name']} | {knowledge[p['id']]} |" for p in taxonomy["knowledge_points"]]
        lines += ["", "## approved 难度分布", "", "| difficulty | 数量 |", "| --- | ---: |"]
        lines += [f"| {number} | {difficulty[number]} |" for number in range(1, 6)]
        for title, vocabulary, counts in (("ability_tag", taxonomy["ability_tags"], ability),
                                          ("method_tag", taxonomy["method_tags"], method)):
            lines += ["", f"## approved {title} 分布", "", "| 标签 | 数量 |", "| --- | ---: |"]
            lines += [f"| {tag} | {counts[tag]} |" for tag in vocabulary]
        lines += ["", "## 暂无金标准题的知识点", ""]
        lines += [f"- {p['id']} {p['name']}：暂无金标准题。" for p in taxonomy["knowledge_points"] if not knowledge[p["id"]]]
        lines += ["", "K007 暂无金标准题，需要 Batch 002 定向补充。" if not knowledge["K007"] else "K007 已有金标准题。",
                  "其他节点先完成本批审核，完成后仍为0的节点再定向补充。本阶段不处理 Batch 002。", "",
                  "## 数据库边界", "", "不写数据库，不调用 LLM，正式业务未切换到 function_v2。",
                  "临时库验收脚本独立运行，自动创建和清理隔离 SQLite，不修改真实 math_ai.db 或 attempts。", ""]
        if len(approved) == len(self.candidates) and approved:
            lines += ["## Batch 001 批准结论", "",
                      "用户已完成人工审核，批准记录中的 manual_user 指用户确认，不代表第二次 AI 审核。",
                      "Batch 001 可以作为第一批金标准题，但 function_v2 尚不能认为题库覆盖完整。", ""]
        return "\n".join(lines)


def approve_confirmed_batch(snapshot: Path, reviews: Path, approved: Path, report: Path,
                            *, expected_count: int = 29, review_notes: str | None = None) -> ReviewSession:
    """Apply the user's explicit completed review only after whole-batch preflight.

    No CLI automatically invokes this: caller needs the user's prior approval.
    """
    session = ReviewSession(snapshot, reviews, approved, report)
    errors = []
    if len(session.candidates) != expected_count:
        errors.append(f"候选数量应为{expected_count}，实际为{len(session.candidates)}")
    fingerprints = [row.get("fingerprint") for row in session.candidates]
    if len(set(fingerprints)) != len(fingerprints):
        duplicate = {value for value, count in Counter(fingerprints).items() if count > 1}
        errors.append("fingerprint 重复：" + ", ".join(row['id'] for row in session.candidates if row.get('fingerprint') in duplicate))
    for row in session.candidates:
        result = validate_candidate(row)
        if not result["can_approve"]:
            errors.append(f"{row['id']}：" + "; ".join(result["errors"] + result["warnings"]))
    if errors:
        raise ValueError("批准前校验失败：\n" + "\n".join(errors))
    notes = review_notes or "用户已基于可读版题目完成人工审核，确认题干、选项、答案、解析及题目分类可接受。"
    events = []
    for original in session.candidates:
        event = deepcopy(original)
        event.update(quality_status="approved", annotation_status="confirmed", reviewed_by="manual_user",
                     reviewed_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                     review_decision="approve", candidate_snapshot_sha256=session.digest,
                     review_notes=list(original.get("review_notes", [])) + [notes],
                     review_confirmation={"reviewer": "manual_user", "confirmed": True,
                                          "checklist": list(CHECKLIST), "basis": "explicit_user_attestation"})
        session._validate_event(event)
        events.append(event)
    if hashlib.sha256(session.snapshot.read_bytes()).hexdigest() != session.digest:
        raise ValueError("批准前快照发生变化。")
    atomic_write(session.reviews, session._jsonl(session.events + events))
    session.events += events
    session.latest.update({event["id"]: event for event in events})
    session.save_outputs()
    return session
