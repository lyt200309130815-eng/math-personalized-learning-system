"""Generate geometry review documents and pending decisions without DB writes."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.geometry_review import build_review_pack


if __name__ == '__main__':
    bank = ROOT / 'data/question_bank'
    result = build_review_pack(bank / 'geometry_v1_1a', ROOT / 'reports', bank / 'geometry_v1_1b',
                               bank / 'review_decisions/geometry_review_decisions.jsonl', ROOT / 'math_ai.db')
    print(json.dumps({k: result[k] for k in ['clean_candidates', 'warning_candidates', 'batch_counts',
                                           'asset_roles', 'unlinked_pending', 'duplicate_group_counts',
                                           'decision_counts', 'production_db_modified']}, ensure_ascii=False, indent=2))
