"""Explicit production CLI reusing the tested V0.9 migration transaction."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.database import get_connection, DATABASE_PATH
from database.taxonomy_migration import migrate_function_v2, protected_snapshot
from scripts.function_v2_dry_run import load_gold
from services.question_review import atomic_write


def inspect_database(path):
    with closing(get_connection(path, read_only=True)) as connection:
        snapshot = protected_snapshot(connection)
        tables = [dict(row) for row in connection.execute('PRAGMA table_list')]
    return dict(database_path=str(Path(path).resolve()), table_list=tables,
                questions_count=snapshot['questions_count'], attempts_count=snapshot['attempts_count'],
                attempts_digest=snapshot['attempts_digest'])


def run_migration(path, report_path):
    path = Path(path).resolve()
    gold = load_gold()
    before = inspect_database(path)
    atomic_write(report_path, json.dumps({'before': before, 'status': 'prepared'}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'before': before}, ensure_ascii=True, indent=2))
    result = migrate_function_v2(path, gold, allow_production=True)
    after = inspect_database(path)
    if any(before[key] != after[key] for key in ('attempts_count', 'attempts_digest')):
        raise ValueError('迁移后 attempts 保护检查失败。')
    report = dict(before=before, after=after, migration=result, status='verified')
    atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DATABASE_PATH)
    parser.add_argument('--production', action='store_true', required=True,
                        help='明确执行正式迁移；脚本不删除或重新评分历史记录')
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/function_v2_production_validation.json')
    args = parser.parse_args()
    run_migration(args.database, args.report)
