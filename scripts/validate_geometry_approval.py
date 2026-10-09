"""Actual recovery integration acceptance on a disposable SQLite backup."""
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from database.database import get_connection,get_approved_questions,record_attempt
from database.training_sessions import load_session,save_session
from services.geometry_production_approval import integrate,baseline
from services.geometry_recovery import production_audit
from services.geometry_quality import geometry_difficulty_range
from services.adaptive_training import start_training_session,get_next_question,submit_training_answer,exposure_tokens
from services.diagnostic import generate_diagnostic_test
from services.mastery import calculate_knowledge_mastery
from services.question_assets import visible_assets,readable_asset,geometry_trainable
from services.math_normalizer import audit_question
from services.recommendation import generate_recommendation
from services.profile import build_profile_data


def answer(q):
    return q['answer'] if q['question_type']=='single_choice' else json.dumps(q['correct_answers']) if q['question_type']=='multiple_choice' else q['canonical_answer'] if q['question_type']=='fill_blank' else '根据题目条件写出推理与计算过程。'


def validate():
    folder=ROOT/'tmp'/('geometry_v1_1e_validation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    folder.mkdir(parents=True);path=folder/'validation.db'
    original,_=baseline(ROOT/'math_ai.db')
    with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as src,closing(get_connection(path)) as dst:src.backup(dst)
    pool=get_approved_questions(database_path=path,taxonomy_version='geometry_v1')
    if len(pool)==123:
        integrate(path,output=folder/'migration')
        pool=get_approved_questions(database_path=path,taxonomy_version='geometry_v1')
    audit,_=production_audit(path)
    state=generate_diagnostic_test('TEST_GEO_V11E','geometry_v1',database_path=path)
    planned={q['id']:q for q in state['pool']}
    diagnostic=[planned[qid] for qid in state['planned_question_ids']]
    assert 12<=len(diagnostic)<=15
    assert len({q['knowledge_point_id'] for q in diagnostic})==10
    assert len({q['question_type'] for q in diagnostic})==4
    bands={}
    for label,values,expected in [('low',(0,0,0,0,0,0),(1,2)),('medium',(1,1,1,1,0,0),(2,3)),
                                   ('high',(0,1,1,1,1,1),(3,4)),('stable',(1,1,1,1,1,1),(4,5))]:
        student='TEST_GEO_V11E_'+label
        # Give prerequisites independent objective evidence; no algorithm mocks.
        for key in ('G003','G005','G006','G007'):
            seeds=sorted([q for q in pool if q['knowledge_point_id']==key and q['question_type']!='subjective' and q['difficulty']==2],key=lambda q:(q['question_type']!='single_choice',q['id']))[:6]
            assert len(seeds)==6,(key,len(seeds))
            for q,correct in zip(seeds,values if key=='G007' else (1,1,1,1,1,1)):
                chosen=answer(q) if correct else next(a for a in q['options'] if a!=q['answer']) if q['question_type']=='single_choice' else 'wrong'
                record_attempt(student,q['id'],chosen,correct,1,database_path=path,taxonomy_version='geometry_v1')
        mastery=calculate_knowledge_mastery(student,'G007',database_path=path,taxonomy_version='geometry_v1')
        assert geometry_difficulty_range(mastery)==expected,(label,mastery)
        session=start_training_session(student,'geometry_v1',target_knowledge_point_id='G007',database_path=path)
        assert session['target_knowledge_point_id']=='G007'
        selected=[];seen=set()
        for _ in range(8):
            q=get_next_question(student,session['id'],database_path=path)
            if q is None:break
            tokens=exposure_tokens(q)
            assert not tokens&seen
            seen.update(tokens)
            selected.append(dict(id=q['id'],knowledge=q['knowledge_point_id'],difficulty=q['difficulty'],type=q['question_type']))
            # Observe fixed simulated mastery bands without fabricating correct answers:
            # low/medium deliberately make objective mistakes; pending tasks remain pending.
            value=answer(q)
            if label in ('low','medium') and q['question_type']=='single_choice':value=next(a for a in q['options'] if a!=q['answer'])
            if label in ('low','medium') and q['question_type']=='multiple_choice':value='["A"]'
            if label in ('low','medium') and q['question_type']=='fill_blank':value='wrong'
            session=submit_training_answer(student,session['id'],q['id'],value,1,database_path=path)
            if session['status']!='active':break
        assert selected
        assert selected[0]['difficulty'] in expected,(label,selected)
        if label=='low':assert all(q['difficulty']<=2 and q['type']!='subjective' for q in selected)
        with closing(get_connection(path,read_only=True)) as conn:stored=load_session(conn,session['id'],student)
        bands[label]=dict(initial_score=mastery['mastery_score'],independent_evidence=mastery['source_evidence_count'],
            initial_band=expected,selected=selected,actual_difficulties=[q['difficulty'] for q in selected],
            type_counts=dict(Counter(q['type'] for q in selected)),status=stored['status'],limitations=stored.get('difficulty_coverage_limitation',[]))
    assert any(q['difficulty']==4 for q in bands['high']['selected'])
    assert any(q['difficulty']==5 for q in bands['stable']['selected'])
    images=Counter(a['role'] for q in pool for a in q.get('diagram_assets',[]))
    recovered=[q for q in pool if q.get('reviewed_by')=='manual_user']
    for q in recovered:
        assert geometry_trainable(q) and not audit_question(q)['issues']
        assert all(readable_asset(a) for a in q['diagram_assets'])
        assert all(a['role']!='solution_diagram' for a in visible_assets(q))
    function=get_approved_questions(database_path=path,taxonomy_version='function_v2')
    assert all(q['knowledge_point_id'].startswith('K') for q in function)
    function_state=generate_diagnostic_test('TEST_GEO_V11E_FUNCTION','function_v2',database_path=path)
    rec=generate_recommendation('TEST_GEO_V11E_FUNCTION',database_path=path,taxonomy_version='function_v2')
    mastery=calculate_knowledge_mastery('TEST_GEO_V11E_FUNCTION','K001',database_path=path,taxonomy_version='function_v2')
    build_profile_data([mastery])
    function_session=start_training_session('TEST_GEO_V11E_FUNCTION','function_v2',target_knowledge_point_id='K001',database_path=path)
    fq=get_next_question('TEST_GEO_V11E_FUNCTION',function_session['id'],database_path=path)
    assert fq and fq['knowledge_point_id'].startswith('K')
    after,_=baseline(ROOT/'math_ai.db');assert original==after
    result=dict(result='PASS',database=str(path),audit=audit,
        diagnostic=dict(student='TEST_GEO_V11E',question_ids=[q['id'] for q in diagnostic],
        knowledge=dict(Counter(q['knowledge_point_id'] for q in diagnostic)),difficulty=dict(Counter(q['difficulty'] for q in diagnostic)),
        question_types=dict(Counter(q['question_type'] for q in diagnostic))),adaptive=bands,
        assets=dict(images),recovery_images=dict(Counter(a['role'] for q in recovered for a in q['diagram_assets'])),
        function_regression=dict(pool=len(function),diagnostic_size=len(function_state['planned_question_ids']),
        training_id=fq['id'],recommendation_target=rec['target_knowledge']['knowledge_point_id'],profile='PASS'),
        production_attempts_unchanged=True)
    (ROOT/'reports/geometry_v1_1e_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':validate()
