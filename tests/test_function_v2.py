"""Real versioned services on disposable databases; no monkeypatched taxonomy."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from runtime_helpers import use_v1_test_config
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.database import (get_connection,get_knowledge_points,get_knowledge_attempts,get_question_mapping,
    get_question_prerequisites,get_approved_questions,get_training_questions,record_attempt,DATABASE_PATH)
from database.taxonomy_migration import migrate_function_v2,validate_graph,SCHEMA
from init_db import initialize_database
from scripts.function_v2_dry_run import load_gold,backup_database,database_summary,simulate_learning_path
from services.mastery import calculate_student_mastery,calculate_knowledge_mastery
from services.recommendation import generate_recommendation,recommend_questions
from services.profile import build_profile_data
from services.feedback import build_feedback_context,build_rule_based_feedback,generate_learning_feedback
from services.question_review import read_jsonl
from settings import get_active_taxonomy_version

ROOT=Path(__file__).resolve().parents[1]


class FunctionV2Tests(unittest.TestCase):
    def setUp(self):
        use_v1_test_config(self)
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'v2.db'
        initialize_database(self.path)
        for q in ('Q001','Q001','Q002','Q003','Q004','Q005','Q006'):
            record_attempt('S001',q,'A',1,1.0,database_path=self.path)
        with closing(get_connection(self.path)) as c:
            self.original_attempts=[tuple(r) for r in c.execute('SELECT * FROM attempts ORDER BY id')]
            self.original_questions=[tuple(r) for r in c.execute('SELECT * FROM questions ORDER BY id')]
        self.gold=load_gold()
        migrate_function_v2(self.path,self.gold)

    def kwargs(self): return dict(database_path=self.path,taxonomy_version='function_v2')

    def train(self,key,count=6,student='TEST',correct=1):
        q=get_approved_questions(key,**self.kwargs())[0]
        for _ in range(count): record_attempt(student,q['id'],q['answer'],correct,1.5,**self.kwargs())
        return q

    def test_all_66_approved_and_15_nodes_present(self):
        self.assertEqual(len(self.gold),66)
        self.assertEqual(len(get_knowledge_points('function_v2',database_path=self.path)),15)
        pool=get_training_questions(**self.kwargs())
        self.assertTrue({q['id'] for q in self.gold} <= {q['id'] for q in pool})
        self.assertEqual(len(pool),72) # six preserved/mapped legacy questions

    def test_batch003_user_audit_and_immutable_candidate(self):
        candidate=ROOT/'data/question_bank/candidates/function_batch_003_original.jsonl'
        self.assertEqual(hashlib.sha256(candidate.read_bytes()).hexdigest(),'f40b4fc5bd93cf2f099b55ba6dc9d0171c2ddb12caf9408335cd6d531d4d4782')
        self.assertTrue(all(q['quality_status']=='reviewed' for q in read_jsonl(candidate)))
        gold=read_jsonl(ROOT/'data/question_bank/approved/function_batch_003_original_approved.jsonl')
        self.assertEqual(len(gold),11)
        for q in gold:
            self.assertEqual(q['reviewed_by'],'manual_user')
            self.assertIn('用户已人工审核原创补缺题，确认题干、选项、答案、解析、知识点和难度可接受。',q['review_notes'])

    def test_eight_schema_tables_and_draft_registration(self):
        with closing(get_connection(self.path)) as c:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({'taxonomy_versions','knowledge_catalog','knowledge_prerequisites','question_knowledge_mappings',
                'question_tags','question_prerequisites','question_sources','taxonomy_migrations'}<=tables)
            self.assertEqual(c.execute('SELECT status FROM taxonomy_versions WHERE version=?',('function_v2',)).fetchone()[0],'draft')
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_graph_no_cycles_self_reference_or_missing_nodes(self):
        points=get_knowledge_points('function_v2',database_path=self.path)
        validate_graph([{**p,'prerequisite_ids':json.loads(p['prerequisite_ids'])} for p in points])
        for invalid in ([{'id':'A','prerequisite_ids':['A']}], [{'id':'A','prerequisite_ids':['B']}],
                        [{'id':'A','prerequisite_ids':['B']},{'id':'B','prerequisite_ids':['A']}]):
            with self.assertRaises(ValueError): validate_graph(invalid)

    def test_every_question_has_one_primary(self):
        for q in get_training_questions(**self.kwargs()):
            mappings=get_question_mapping(q['id'],**self.kwargs())
            self.assertEqual(sum(m['role']=='primary' for m in mappings),1)
        with closing(get_connection(self.path)) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('INSERT INTO question_knowledge_mappings VALUES (?,?,?,?,?)',('function_v2','Q001','K002','primary','approved'))

    def test_related_never_counts_as_mastery_evidence(self):
        record_attempt('RELATED','Q005','B',1,2.0,**self.kwargs())
        points=calculate_student_mastery('RELATED',**self.kwargs())
        self.assertEqual(sum(p['attempt_count'] for p in points),1)
        self.assertEqual(next(p for p in points if p['knowledge_point_id']=='K003')['attempt_count'],1)
        self.assertIsNone(next(p for p in points if p['knowledge_point_id']=='K007')['mastery_score'])

    def test_unapproved_states_cannot_train_or_recommend(self):
        q=self.gold[0]
        for status in ('reviewed','draft','rejected'):
            with closing(get_connection(self.path)) as c:
                with c: c.execute('UPDATE question_knowledge_mappings SET review_status=? WHERE question_id=?',(status,q['id']))
            self.assertNotIn(q['id'],{p['id'] for p in get_training_questions(**self.kwargs())})
            with self.assertRaises(ValueError): record_attempt('UNAPPROVED',q['id'],'A',0,1.0,**self.kwargs())
            self.assertNotIn(q['id'],{p['id'] for p in recommend_questions('NONE',q['primary_knowledge_point_id'],**self.kwargs())})

    def test_no_data_student_all_fifteen_none_and_starts_k001(self):
        points=calculate_student_mastery('S_TEST_NEW',**self.kwargs())
        self.assertEqual(len(points),15)
        self.assertTrue(all(p['mastery_score'] is None and p['mastery_level']=='未评估' for p in points))
        rec=generate_recommendation('S_TEST_NEW',**self.kwargs())
        self.assertEqual(rec['target_knowledge']['knowledge_point_id'],'K001')
        self.assertEqual(rec['target_knowledge']['recommendation_type'],'诊断')
        self.assertTrue(rec['recommended_questions'])

    def test_historical_s001_maps_q005_q006_without_k005_pollution(self):
        points={p['knowledge_point_id']:p for p in calculate_student_mastery('S001',**self.kwargs())}
        self.assertEqual([points[k]['attempt_count'] for k in ('K001','K002','K003','K004')],[2,1,2,2])
        self.assertEqual(sum(p['attempt_count'] for p in points.values()),7)
        self.assertIsNone(points['K005']['mastery_score'])
        self.assertEqual(points['K005']['knowledge_point_name'],'函数奇偶性')

    def test_mastery_formula_and_recent_results_unchanged(self):
        q=self.train('K001',count=5)
        record_attempt('TEST',q['id'],'A',0,1.0,**self.kwargs())
        p=calculate_knowledge_mastery('TEST','K001',**self.kwargs())
        self.assertAlmostEqual(p['overall_accuracy'],5/6)
        self.assertAlmostEqual(p['recent_accuracy'],4/5)
        self.assertAlmostEqual(p['stability'],0.8*(1-0.4))
        self.assertAlmostEqual(p['mastery_score'],.5*(5/6)+.2*.8+.15*.48+.15*(5/6))

    def test_simulated_path_and_core_prerequisite_fallback(self):
        path=simulate_learning_path(self.path)
        self.assertEqual([step['next'] for step in path],['K002','K003','K004'])
        for attempt in get_knowledge_attempts('S_TEST_PATH','K003',**self.kwargs()):
            self.assertEqual(get_question_prerequisites(attempt['question_id'],**self.kwargs()),[])
        self.assertEqual(generate_recommendation('TEST',**self.kwargs())['target_knowledge']['knowledge_point_id'],'K001')
        self.train('K001')
        self.assertEqual(generate_recommendation('TEST',**self.kwargs())['target_knowledge']['knowledge_point_id'],'K002')
        self.train('K002')
        self.assertEqual(generate_recommendation('TEST',**self.kwargs())['target_knowledge']['knowledge_point_id'],'K003')
        self.train('K003',correct=0)
        rec=generate_recommendation('TEST',**self.kwargs())
        # Every recommended target must have its necessary core prerequisites satisfied.
        graph={p['id']:json.loads(p['prerequisite_ids']) for p in get_knowledge_points('function_v2',database_path=self.path)}
        for parent in graph[rec['target_knowledge']['knowledge_point_id']]:
            self.assertGreaterEqual(calculate_knowledge_mastery('TEST',parent,**self.kwargs())['mastery_score'],.6)
        self.assertEqual(recommend_questions('UNTRAINED','K014',**self.kwargs()),[])
        self.train('K001',student='BLOCKED');self.train('K002',student='BLOCKED',correct=0)
        self.train('K014',student='BLOCKED',correct=0)
        self.assertEqual(generate_recommendation('BLOCKED',**self.kwargs())['target_knowledge']['knowledge_point_id'],'K002')

    def test_question_prerequisite_blocks_then_unlocks(self):
        self.train('K001');self.train('K002')
        self.assertEqual(get_question_prerequisites('Q005',**self.kwargs()),['K007'])
        before={q['id'] for q in recommend_questions('TEST','K003',limit=50,**self.kwargs())}
        self.assertNotIn('Q005',before)
        self.train('K007')
        after={q['id'] for q in recommend_questions('TEST','K003',limit=50,**self.kwargs())}
        self.assertIn('Q005',after)

    def test_difficulty_preference_and_recent_duplicate_avoidance(self):
        q= recommend_questions('TEST','K001',limit=1,**self.kwargs())[0]
        self.assertIn(q['difficulty'],(1,2))
        actual=next(p for p in get_approved_questions('K001',**self.kwargs()) if p['id']==q['id'])
        record_attempt('TEST',q['id'],actual['answer'],1,1.0,**self.kwargs())
        selected=recommend_questions('TEST','K001',limit=5,**self.kwargs())
        self.assertNotEqual(selected[0]['id'],q['id'])
        self.assertEqual(len(selected),len({p['id'] for p in selected}))

    def test_no_eligible_target_friendly_deterministic_fallback(self):
        with closing(get_connection(self.path)) as c:
            with c: c.execute("UPDATE question_knowledge_mappings SET review_status='draft' WHERE taxonomy_version='function_v2' AND knowledge_point_id='K001'")
        result=generate_recommendation('NEW',**self.kwargs())
        self.assertEqual(result['recommended_questions'],[])
        self.assertIn('暂缺',result['message'])
        self.assertEqual(result,generate_recommendation('NEW',**self.kwargs()))

    def test_profile_fifteen_points_and_none_not_zero(self):
        profile=build_profile_data(calculate_student_mastery('NEW',**self.kwargs()))
        self.assertEqual(len(profile['points']),15)
        self.assertEqual(profile['chart'],[])
        self.assertTrue(all(p['mastery_display']=='未评估' for p in profile['points']))

    def test_feedback_mock_never_changes_results_or_sends_identity(self):
        context=build_feedback_context('PRIVATE_TEST_ID',**self.kwargs());before=deepcopy(context)
        text=build_rule_based_feedback(context)
        with patch('services.feedback.generate_text',return_value=text) as provider:
            self.assertEqual(generate_learning_feedback('PRIVATE_TEST_ID',context=context),text)
        prompt=provider.call_args.args[0]
        self.assertNotIn('PRIVATE_TEST_ID',prompt)
        self.assertNotIn(str(self.path),prompt)
        self.assertEqual(context,before)

    def test_v1_environment_switch_and_fallback(self):
        with patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2'}):
            self.assertEqual(len(calculate_student_mastery('S001')),15)
            self.assertEqual(len(get_training_questions()),72)
        with patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v1'}):
            self.assertEqual(get_active_taxonomy_version(),'function_v1')
            self.assertEqual(len(calculate_student_mastery('S001')),5)
            self.assertEqual(len(get_training_questions()),6)
            self.assertEqual(calculate_knowledge_mastery('S001','K005')['attempt_count'],2)

    def test_migration_idempotent_and_digest_change_rejected(self):
        before=database_summary(self.path)
        self.assertEqual(migrate_function_v2(self.path,self.gold),{'inserted':0,'skipped':66})
        self.assertEqual(database_summary(self.path),before)
        modified=deepcopy(self.gold);modified[0]['review_notes'].append('different audit')
        with self.assertRaisesRegex(ValueError,'摘要改变'):migrate_function_v2(self.path,modified)

    def test_legacy_attempts_questions_completely_preserved(self):
        with closing(get_connection(self.path)) as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM attempts ORDER BY id')],self.original_attempts)
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM questions WHERE id IN (?,?,?,?,?,?) ORDER BY id',tuple(f'Q00{i}' for i in range(1,7)))],self.original_questions)

    def test_production_path_refused_without_modification(self):
        digest=hashlib.sha256(DATABASE_PATH.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):migrate_function_v2(DATABASE_PATH,self.gold)
        self.assertEqual(hashlib.sha256(DATABASE_PATH.read_bytes()).hexdigest(),digest)

    def test_migration_rejects_unapproved_input_before_writing(self):
        before=database_summary(self.path)
        for status in ('reviewed','draft','rejected'):
            rows=deepcopy(self.gold);rows[0]['quality_status']=status
            with self.assertRaises(ValueError): migrate_function_v2(self.path,rows)
        self.assertEqual(database_summary(self.path),before)

    def test_mid_migration_conflict_rolls_back_schema_and_new_questions(self):
        path=Path(self.temp.name)/'rollback.db';initialize_database(path)
        collision=self.gold[0]
        with closing(get_connection(path)) as c:
            with c:
                c.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (collision['id'],'保留题干',json.dumps(dict(zip('ABCD',('1','2','3','4')))),
                           'A','保留解析','K001',1,'concept_understanding','single_choice',60))
            original=[tuple(r) for r in c.execute('SELECT * FROM questions ORDER BY id')]
        with self.assertRaisesRegex(ValueError,'ID与原库冲突'): migrate_function_v2(path,self.gold)
        with closing(get_connection(path)) as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM questions ORDER BY id')],original)
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='taxonomy_versions'").fetchone())

    def test_backup_api_includes_committed_wal_contents(self):
        source=Path(self.temp.name)/'wal.db'; target=Path(self.temp.name)/'copy.db'
        with closing(sqlite3.connect(source)) as c:
            c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE TABLE test(value TEXT)')
            c.execute('INSERT INTO test VALUES (?)',('WAL内容',));c.commit()
            backup_database(source,target)
            with closing(sqlite3.connect(target)) as copied:
                self.assertEqual(copied.execute('SELECT value FROM test').fetchone()[0],'WAL内容')

    def test_all_four_streamlit_pages_on_real_v2_interfaces_no_api(self):
        with patch.dict(os.environ,{'MATH_AI_DATABASE_PATH':str(self.path),'ACTIVE_TAXONOMY_VERSION':'function_v2',
                                   'DEEPSEEK_API_KEY':'','OPENAI_API_KEY':'','GEMINI_API_KEY':''}), \
             patch('services.feedback.generate_text',side_effect=AssertionError('禁止联网')):
            for page in ('training','profile','recommendation','feedback'):
                app=AppTest.from_file(str(ROOT/f'pages/{page}.py')).run()
                self.assertFalse(app.exception,page)
            app=AppTest.from_file(str(ROOT/'pages/training.py')).run()
            app.button[0].click().run()
            q=app.session_state['adaptive_training_state']['current_question']
            app.radio[0].set_value(q['answer']).run()
            next(b for b in app.button if b.label=='提交答案').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state['adaptive_training_state']['submitted'])
            self.assertIsNotNone(app.session_state['adaptive_training_state']['answers'][0]['attempt_id'])
            with closing(get_connection(self.path)) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],8)
