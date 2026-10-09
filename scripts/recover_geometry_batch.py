"""Offline V1.1D review package; deliberately no approval/import flags."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.geometry_recovery import build_recovery

if __name__ == '__main__':
    result = build_recovery()
    print(json.dumps({k: v for k, v in result.items() if k != 'production_audit'}, ensure_ascii=False, indent=2))
