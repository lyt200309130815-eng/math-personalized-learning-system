"""Review-boundary checks and synthetic four-type activation in a temporary DB."""
from contextlib import closing
from pathlib import Path
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from scripts.expand_multitype_question_bank import BATCHES, read_rows
from scripts.inspect_multitype_sources import protected_snapshot
from scripts.function_v2_dry_run import load_gold
from services.question_importer import import_questions, activate_training_questions
from database.database import get_connection, get_approved_questions
from database.taxonomy_migration import migrate_function_v2
from database.four_type import migrate_four_type
from init_db import initialize_database
from question_bank_helpers import approved
from test_multitype_expansion import multi, subjective
from test_multi_type import typed_fixture


def validate():
    before=protected_snapshot()
    rows=[q for kind,batch in BATCHES.items() for q in read_rows(ROOT/f'data/question_bank/candidates/function_{kind}_batch_{batch}.jsonl')]
    with tempfile.TemporaryDirectory(prefix='math_ai_v1_0d_1_') as folder:
        path=Path(folder)/'isolated.db'
        initialize_database(path);migrate_function_v2(path,load_gold())
        with closing(get_connection(path)) as c:
            historical=[tuple(r) for r in c.execute('SELECT * FROM attempts ORDER BY id')]
        first=migrate_four_type(path);repeat=migrate_four_type(path)
        bank=import_questions(rows,database_path=path)
        assert bank['inserted']==0 and bank['rejected']==len(rows)
        data=path.read_bytes()
        try:activate_training_questions(rows,database_path=path)
        except ValueError:pass
        else:raise AssertionError('reviewed batch activated')
        assert data==path.read_bytes()
        # Only explicit synthetic test fixtures simulate an approved contract.
        fixtures=[approved(id='SYNTHETIC_SINGLE'),multi(),typed_fixture(),subjective()]
        bank_fixture=import_questions(fixtures,database_path=path)
        active=activate_training_questions(fixtures,database_path=path)
        assert bank_fixture['inserted']==4 and active['inserted']==4
        got={q['id']:q for q in get_approved_questions(database_path=path,taxonomy_version='function_v2')}
        assert got['MULTI_TEST']['correct_answers']==['A','B']
        assert got['SUBJECT_TEST']['sub_questions']==subjective()['sub_questions']
        with closing(get_connection(path)) as c:
            assert historical==[tuple(r) for r in c.execute('SELECT * FROM attempts ORDER BY id')]
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        result={'stage':'V1.0D.1','temporary_database_only':True,'temporary_database_removed_on_exit':True,
                'migration_applied':first['applied'],'repeat_migration_applied':repeat['applied'],
                'reviewed_candidates_tested':len(rows),'reviewed_rejected':bank['rejected'],
                'reviewed_training_imports':0,'synthetic_fixture_types_tested':4,
                'synthetic_bank_inserted':bank_fixture['inserted'],'synthetic_training_inserted':active['inserted'],
                'temporary_historical_attempts_unchanged':True,'foreign_keys_valid':True}
    assert protected_snapshot()==before
    original=json.loads((ROOT/'tmp/v1_0d_1/protected_before.json').read_text(encoding='utf-8'))
    assert before==original
    result.update(production_database_modified=False,historical_attempts_modified=False,
                  approved_files_modified=False,source_docx_modified=False)
    output=ROOT/'reports/v1_0d_1_validation.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':validate()
