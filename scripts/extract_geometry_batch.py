"""Run V1.1A offline geometry staging without importing a database."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.source_extractors.geometry_pipeline import build_pipeline


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='立体几何候选题与原始图形提取（不入库）')
    parser.add_argument('--source', type=Path, default=ROOT / 'data/raw_sources/geometry')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/question_bank/geometry_v1_1a')
    args = parser.parse_args()
    result = build_pipeline(args.source, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=False, indent=2))
