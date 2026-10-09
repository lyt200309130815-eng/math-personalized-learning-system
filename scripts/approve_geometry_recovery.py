"""Explicit V1.1E production approval entry point."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.geometry_production_approval import integrate,baseline,BATCH,prepare_approval,load_geometry_rows
from services.geometry_review import read_rows
from database.database import get_connection
from contextlib import closing

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,default=ROOT/'math_ai.db')
    parser.add_argument('--apply-production',action='store_true')
    args=parser.parse_args()
    if args.apply_production:
        result=integrate(args.database,allow_production=True)
        print(json.dumps({k:v for k,v in result.items() if k!='duplicate_audit'},ensure_ascii=False,indent=2))
    else:
        before,_=baseline(args.database)
        with closing(get_connection(args.database,read_only=True)) as conn:
            reviewed,audit=prepare_approval(read_rows(BATCH),load_geometry_rows(conn))
        print(json.dumps(dict(baseline=before,gate_passed=sum(q['trainable'] for q in reviewed),
            blocked=[dict(id=q['id'],reasons=q['production_gate_reasons']) for q in reviewed if not q['trainable']],
            duplicate_count=sum(bool(q['duplicates']) for q in audit)),ensure_ascii=False,indent=2))
