"""Read-only source/database inspection for V1.0D.1."""
from pathlib import Path
import sys
import json
import hashlib
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.database import get_connection, get_approved_questions
from services.source_extractors.docx_question_extractor import read_docx_blocks
from services.source_extractors.docx_multi_type_extractor import extract_multi_type_questions


def protected_snapshot():
    files = [ROOT/'math_ai.db'] + list((ROOT/'data/question_bank/approved').glob('*.jsonl'))
    files += list((ROOT/'data/raw_sources/function').glob('*.docx'))
    with closing(get_connection(ROOT/'math_ai.db', read_only=True)) as conn:
        tables = {r[0]: hashlib.sha256(json.dumps([list(v) for v in conn.execute('SELECT * FROM "'+r[0]+'" ORDER BY rowid')],
                         ensure_ascii=False).encode()).hexdigest()
                  for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    return {'files': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, 'tables': tables}


if __name__ == '__main__':
    folder = ROOT/'tmp/v1_0d_1'
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = folder/'protected_before.json'
    if not snapshot.exists(): snapshot.write_text(json.dumps(protected_snapshot(), indent=2), encoding='utf-8')
    with closing(get_connection(ROOT/'math_ai.db', read_only=True)) as conn:
        schema = [list(r) for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")]
    (folder/'schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')
    approved = get_approved_questions(database_path=ROOT/'math_ai.db', taxonomy_version='function_v2')
    print('Current approved static:', len([q for q in approved if q['source_type'] != 'generated_template']))
    rows = []
    for p in sorted((ROOT/'data/raw_sources/function').glob('*.docx')):
        blocks = read_docx_blocks(p)
        (folder/(p.stem+'.txt')).write_text('\n'.join(f"{b['index']}: {b['text']}" for b in blocks), encoding='utf-8')
        rows.extend(extract_multi_type_questions(p.relative_to(ROOT)))
        print(p.name, len(blocks), 'paragraphs')
    (folder/'scan.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
