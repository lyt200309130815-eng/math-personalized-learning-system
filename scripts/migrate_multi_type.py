"""Local V1.0D schema migration; no candidate import or network requests."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database.multi_type import migrate_multi_type


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path)
    args=parser.parse_args()
    print(migrate_multi_type(args.database))
