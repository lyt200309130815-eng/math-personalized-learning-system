"""Apply only the idempotent V1.0B training-session schema migration."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.training_sessions import migrate_training_sessions
from settings import get_database_path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=get_database_path())
    args = parser.parse_args()
    print(json.dumps(migrate_training_sessions(args.database), ensure_ascii=False))
