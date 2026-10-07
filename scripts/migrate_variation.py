"""Run the idempotent local V1.0C migration; no network or question harvesting."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database.variation import migrate_variation


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database',type=Path)
    args = parser.parse_args()
    migrate_variation(args.database)
    print('V1.0C migration 完成；历史题目与学习记录保留。')
