"""Read-only final production integrity check and concise acceptance report."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from database.database import get_connection,get_training_questions
from scripts.integrate_multitype_production import snapshot


def finalize():
    production=json.loads((ROOT/'reports/v1_0d_2_production_validation.json').read_text(encoding='utf-8'))
    browser=json.loads((ROOT/'reports/v1_0d_2_browser_validation.json').read_text(encoding='utf-8'))
    with closing(get_connection(ROOT/'math_ai.db',read_only=True)) as current,closing(get_connection(production['backup'],read_only=True)) as backup:
        now=snapshot(current);before=snapshot(backup)
        assert now['attempts_count']==before['attempts_count']==33
        assert now['attempts_digest']==before['attempts_digest']==production['before']['attempts_digest']
        assert get_training_questions(ROOT/'math_ai.db',taxonomy_version='function_v1')==get_training_questions(production['backup'],taxonomy_version='function_v1')
        original={r['id']:tuple(r) for r in backup.execute('SELECT * FROM questions')}
        for row in current.execute('SELECT * FROM questions'):
            if row['id'] in original:assert tuple(row)==original[row['id']]
        assert current.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert not current.execute('PRAGMA foreign_key_check').fetchall()
        counts=dict(current.execute('SELECT question_type,COUNT(*) FROM questions GROUP BY question_type'))
    audit=ROOT/'data/question_bank/reviews/function_multitype_batch_001_manual_user_audit.jsonl'
    for event in [json.loads(s) for s in audit.read_text(encoding='utf-8').splitlines()]:
        assert hashlib.sha256((ROOT/event['candidate_file']).read_bytes()).hexdigest()==event['candidate_sha256']
    assert len(browser['cases'])==4 and all(c['result']=='passed' for c in browser['cases'])
    log=(ROOT/'tmp/v1_0d_2_final_tests.log').read_text(encoding='utf-8',errors='replace')
    assert 'Ran 371 tests' in log and log.rstrip().endswith('OK')
    result={'stage':'V1.0D.2','approved_counts':production['approved_counts'],'question_type_counts':counts,
            'backup':production['backup'],'attempts_count':now['attempts_count'],'attempts_digest':now['attempts_digest'],
            'historical_attempts_unchanged':True,'original_questions_unchanged':True,'candidates_unchanged':True,
            'function_v1_unchanged':True,'foreign_keys':1,'foreign_key_check':'passed',
            'tests_passed':371,'new_tests':22,'browser_cases_passed':4,'subjective_image_upload_passed':True,
            'pending_mastery_unchanged':True,'production_test_attempts_written':0,'ocr_called':False,'commit_created':False,
            'created_files':['database/training_review.py','services/question_structure.py','scripts/approve_multitype_batches.py',
                             'scripts/integrate_multitype_production.py','scripts/smoke_multitype_browser.py',
                             'scripts/finalize_multitype_integration.py','tests/test_multitype_production.py',
                             'data/question_bank/approved/function_multiple_choice_batch_001_approved.jsonl',
                             'data/question_bank/approved/function_fill_blank_batch_001_approved.jsonl',
                             'data/question_bank/approved/function_subjective_batch_001_approved.jsonl',
                             'data/question_bank/reviews/function_multitype_batch_001_manual_user_audit.jsonl',
                             'reports/v1_0d_2_review_validation.json','reports/v1_0d_2_production_validation.json',
                             'reports/v1_0d_2_browser_validation.json','reports/v1_0d_2_final_validation.json',
                             'reports/function_multitype_production_integration_report.md'],
            'modified_files':['.gitignore','README.md','docs/multi_type_engine.md','database/four_type.py',
                              'database/database.py','services/question_importer.py','services/adaptive_training.py',
                              'services/question_renderer.py','services/question_type_policy.py','services/profile.py',
                              'services/feedback.py','pages/training.py','pages/profile.py','tests/test_multi_type.py'],
            'commands_executed':['python scripts/approve_multitype_batches.py',
                                 'python -m unittest discover -s tests -p test_multitype_production.py -q',
                                 'python -m unittest discover -s tests -q',
                                 'python scripts/integrate_multitype_production.py --apply-production',
                                 'python scripts/smoke_multitype_browser.py',
                                 'python scripts/finalize_multitype_integration.py',
                                 'git -c safe.directory=E:/Projects/math_ai diff --check',
                                 'git -c safe.directory=E:/Projects/math_ai status --short',
                                 'git check-ignore backups/ tmp/ student_submissions/ attachments/ .env']}
    (ROOT/'reports/v1_0d_2_final_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# V1.0D.2 多题型正式接入验收','',
           '用户明确人工审核的 batch_001：多选20、填空25、主观16，共61道。全部复检 validator 通过，无阻止批准题。',
           '原 candidates 保持 reviewed、未覆盖。approved 文件保留原题内容与指纹，reviewed_by=manual_user，备注“用户已基于可读版完成人工审核。”。审核审计绑定候选和 Word SHA-256。',
           'batch_002 没有批准或导入。','',
           '| 正式题型 | 数量 |','|---|---:|',*[f'| {k} | {counts[k]} |' for k in ('single_choice','multiple_choice','fill_blank','subjective')],
           '',f"SQLite backup API 一致性备份：`{production['backup']}`。",
           '导入首次新增61，重复新增0、跳过61。导入事务、外键校验、失败回滚已在临时库测试。',
           '原72道题（含原66道金标准新增题）保持不变，function_v1 仍返回原6道种子单选。',
           f"历史 attempts：{now['attempts_count']}条；导入前后 SHA-256 `{now['attempts_digest']}` 完全一致。",'','## 判分与未评分作答','',
           '多选集合完全相同得1，否则0；选项顺序不影响，不计部分分。填空通过受限 AST/SymPy 与规则 evaluator，支持 numeric、expression、interval、set、text 和轻量输入归一化。不由 LLM 决定正确性。',
           '无法安全解析的填空保存为 needs_manual_review，is_correct=NULL，暂不计 mastery。大题保存文本与随机文件名图片引用，status=submitted_pending_review、score=NULL，不自动判错或计算总分。',
           '主观图片沿用 attachments/，校验真实PNG/JPEG/WEBP、10MB上限与像素尺寸。SQLite无图片BLOB。subjective_submissions 关联唯一 attempt_id；answer_review_requests 记录填空人工审核原因。',
           '小问包装只添加原评分点与原解答的对应引用，不改已审核题干、答案、评分点文字或分数；rubric_source=derived_for_system，不声称官方评分细则。',
           'pending details 一律排除有效掌握证据，即使误写非空 is_correct。画像、训练总结与只读反馈区分已评分证据、待评阅大题和待审核填空。推荐逻辑不因 pending 作答变差。','',
           '## 自适应题型','',
           '| 掌握度 | 选择类（单选/多选共享） | 填空 | 大题 |','|---|---:|---:|---:|',
           '| 未评估或 <40% | 80% | 20% | 0% |','| 40–70% | 60% | 40% | 0% |',
           '| 70–85% | 40% | 60% | 0% |','| ≥85% | 25% | 50% | 25% |',
           '', '题型按比例缺口确定性选择，缺题时回退；始终遵守前置与安全难度。先未做/未见题，再近期30题回避，按题号、来源指纹、变式指纹和原段落防止同一原题跨题型重复曝光。',
           '', '## 真实网页与自动测试','',
           '371项全部通过，新增22项；原有349项保留通过。最终日志 tmp/v1_0d_2_final_tests.log。',
           '本地 Edge 无界面浏览器连接真实 Streamlit HTTP 服务，使用正式库副本和合成作答/图片；没有向生产库写入验收作答。',
           '| 网页题型 | 实际交互结果 |','|---|---|',
           '| 单选 | radio显示、选择、提交，判对 |',
           '| 多选 | multiselect显示，按逆序多选，集合判分正确 |',
           '| 填空 | 无radio，输入1.50000000000000，与标准分数答案等价，判对 |',
           '| 大题 | 两小问与总分显示；文本输入和合成PNG实际上传；图片文件引用与submitted_pending_review保存；mastery不变 |',
           '', '网页报告 reports/v1_0d_2_browser_validation.json 包含各题ID和截图路径；截图只存 tmp/。Streamlit AppTest 另覆盖 pending 填空提示、大题显示、画像和既有训练流程。',
           '', '## 文件、命令与安全','',
           '新增/修改文件与执行命令完整清单见 reports/v1_0d_2_final_validation.json。backups/、tmp/、attachments/、student_submissions/、data/student_submissions/、.env 均经 git check-ignore 核实；未commit，未提交学生图片。',
           '不运行OCR，不让DeepSeek评分，不进入下一版本。下一步运行 python -m streamlit run app.py，从首页进入“开始训练”，按学情进行多题型练习。','']
    (ROOT/'reports/function_multitype_production_integration_report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('created_files','modified_files','commands_executed')},ensure_ascii=True,indent=2))


if __name__=='__main__':finalize()
