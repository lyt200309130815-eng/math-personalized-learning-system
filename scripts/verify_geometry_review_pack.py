"""Verify the saved review pack against metadata, including multi-image order."""
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.geometry_review import W, database_snapshot, paragraph_number, read_rows, verify_docx


def verify_pack(root=ROOT):
    data = root / 'data/question_bank/geometry_v1_1b'
    questions = read_rows(data / 'questions_review.jsonl')
    assets = read_rows(data / 'asset_verification.jsonl')
    by_id = {a['id']: a for a in assets}
    doc_checks = []
    for batch in range(1, 7):
        path = root / f'reports/geometry_review_batch_{batch:02}.docx'
        checked = verify_docx(path)
        rows = [q for q in questions if q['batch'] == batch]
        expected = sum(len(by_id[asset_id]['resources']) for q in rows for asset_id in q['review_asset_ids'])
        assert checked['embedded_images'] == expected, path
        with ZipFile(path) as archive:
            text = ''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
        assert text.count('Question ID: ') == len(rows), path
        for q in rows:
            assert q['id'] in text
            labels = [label for label in checked['image_labels'] if any(aid in label for aid in q['review_asset_ids'])]
            expected_ids = [aid for aid in q['review_asset_ids'] for _ in by_id[aid]['resources']]
            assert len(labels) == len(expected_ids), q['id']
            assert all(aid in label for aid, label in zip(expected_ids, labels)), q['id']
            positions = [paragraph_number(by_id[aid]) for aid in q['review_asset_ids']]
            assert positions == sorted(positions), q['id']
        doc_checks.append({k: v for k, v in checked.items() if k != 'image_labels'})
    for name, rows, marker in [
            ('geometry_warning_candidates_review.docx', [q for q in questions if q['review_group'] == 'warning_candidates'], 'Question ID: '),
            ('geometry_unlinked_assets_review.docx', [a for a in assets if a['question_id'] is None], 'asset_id: ')]:
        path = root / 'reports' / name
        checked = verify_docx(path)
        with ZipFile(path) as archive:
            text = ''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
        assert text.count(marker) == len(rows), name
        assert all(row['id'] in text for row in rows), name
        if 'warning' in name:
            assert 'warning_type:' in text and 'warning_field:' in text and 'original_text' in text and 'normalized_text:' in text
            assert 'requires_source_check' in text
        doc_checks.append({k: v for k, v in checked.items() if k != 'image_labels'})
    original_questions = read_rows(root / 'data/question_bank/geometry_v1_1a/questions.jsonl')
    original_assets = read_rows(root / 'data/question_bank/geometry_v1_1a/diagram_assets.jsonl')
    warning_ids = {q['id'] for q in questions if q['review_group'] == 'warning_candidates'}
    assert all(q['id'] in warning_ids for q in original_questions if q['extraction_warnings'])
    assert {q['id'] for q in questions} == {q['id'] for q in original_questions}
    original_links = {a['id']: a['question_id'] for a in original_assets}
    assert all(a['question_id'] == original_links[a['id']] for a in assets)
    assert all(a['human_action'] == 'pending' for a in assets if a['question_id'] is None)
    assert all(not a['student_render_enabled'] for a in assets)
    decisions = read_rows(root / 'data/question_bank/review_decisions/geometry_review_decisions.jsonl')
    assert len(decisions) == len(questions) + len(assets)
    assert all(d['decision'] == 'pending' for d in decisions), '当前首轮审核应全部pending'
    summary = json.loads((data / 'review_summary.json').read_text(encoding='utf-8'))
    assert database_snapshot(root / 'math_ai.db') == summary['database_before'], '真实数据库变化'
    return {'verified_documents': doc_checks, 'total_questions': len(questions),
            'associated_assets': sum(a['question_id'] is not None for a in assets),
            'unlinked_assets': sum(a['question_id'] is None for a in assets), 'decisions_pending': len(decisions),
            'original_warning_candidates_retained': sum(bool(q['extraction_warnings']) for q in original_questions),
            'production_db_modified': False, 'result': 'PASS'}


if __name__ == '__main__':
    print(json.dumps(verify_pack(), ensure_ascii=False, indent=2))
