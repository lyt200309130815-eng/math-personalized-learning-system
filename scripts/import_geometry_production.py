"""Explicit geometry activation after preview and production-gate validation."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.geometry import import_geometry
from services.geometry_review import read_rows

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, default=ROOT / 'math_ai.db')
    parser.add_argument('--apply-production', action='store_true')
    args = parser.parse_args()
    rows = read_rows(ROOT / 'data/question_bank/geometry_v1_1c/approved_ready.jsonl')
    result = import_geometry(args.database, rows, allow_production=args.apply_production)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.apply_production:
        (ROOT / 'reports/geometry_production_import.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
