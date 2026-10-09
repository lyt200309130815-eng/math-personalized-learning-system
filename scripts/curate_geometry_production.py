"""Generate production-ready previews before any database mutation."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.geometry_curation import curate_geometry

if __name__ == '__main__':
    print(json.dumps(curate_geometry(), ensure_ascii=False, indent=2))
