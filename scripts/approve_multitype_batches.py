"""Persist the user's explicit Word review, preserving all candidate snapshots."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.question_validator import validate_candidate,content_fingerprint
from services.question_structure import runtime_metadata
from services.question_review import atomic_write

KINDS=('multiple_choice','fill_blank','subjective')
NOTE='用户已基于可读版完成人工审核。'


def prepare():
    all_rows=[];audit=[];counts={}
    timestamp=datetime.now(timezone.utc).isoformat()
    for kind in KINDS:
        stem=f'function_{kind}_batch_001'
        source=ROOT/f'data/question_bank/candidates/{stem}.jsonl'
        word=ROOT/f'reports/{stem}_可读版.docx'
        if not word.is_file():raise FileNotFoundError(word)
        rows=[json.loads(s) for s in source.read_text(encoding='utf-8').splitlines()]
        picked=[]
        for row in rows:
            validation=validate_candidate(row)
            event={'id':row['id'],'question_type':kind,'candidate_file':str(source.relative_to(ROOT)),
                   'candidate_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                   'word_file':str(word.relative_to(ROOT)),'word_sha256':hashlib.sha256(word.read_bytes()).hexdigest(),
                   'reviewed_by':'manual_user','review_notes':[NOTE],'reviewed_at':timestamp,
                   'candidate_fingerprint':row['fingerprint']}
            if not validation['can_approve']:
                event.update(decision='blocked',errors=validation['errors'],warnings=validation['warnings'])
                audit.append(event);continue
            q=deepcopy(row)
            q.update(quality_status='approved',annotation_status='confirmed',reviewed_by='manual_user',reviewed_at=timestamp,
                     review_confirmation={'reviewer':'manual_user','confirmed':True})
            q['review_notes']=[*q.get('review_notes',[]),NOTE]
            # Runtime packaging adds only subquestion references/canonical aliases.
            # It does not rewrite reviewed stems, answers, rubric text or scores.
            try:
                packaged={**q,**runtime_metadata(q)}
                packaged['fingerprint']=content_fingerprint(packaged)
                packaging_validation=validate_candidate(packaged)
                checked=validate_candidate(q)
                if not checked['can_approve'] or not packaging_validation['can_approve']:
                    raise ValueError(str(checked['errors']+checked['warnings']+packaging_validation['errors']+packaging_validation['warnings']))
            except ValueError as error:
                event.update(decision='blocked',errors=[str(error)],warnings=[]);audit.append(event);continue
            picked.append(q);event.update(decision='approved',approved_fingerprint=q['fingerprint']);audit.append(event)
        destination=ROOT/f'data/question_bank/approved/{stem}_approved.jsonl'
        if destination.exists():
            existing=[json.loads(s) for s in destination.read_text(encoding='utf-8').splitlines()]
            if {(q['id'],q['fingerprint']) for q in existing}!={(q['id'],q['fingerprint']) for q in picked}:
                raise ValueError('已批准快照与当前内容不同，拒绝覆盖。')
        else:atomic_write(destination,''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in picked))
        counts[kind]=len(picked);all_rows.extend(picked)
    audit_path=ROOT/'data/question_bank/reviews/function_multitype_batch_001_manual_user_audit.jsonl'
    if not audit_path.exists():atomic_write(audit_path,''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in audit))
    summary={'approved_counts':counts,'blocked':[e for e in audit if e['decision']=='blocked'],
             'candidate_files_unchanged':True,'reviewed_by':'manual_user','runtime_packaging_only':True}
    (ROOT/'reports/v1_0d_2_review_validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True,indent=2))
    return all_rows


if __name__=='__main__':prepare()
