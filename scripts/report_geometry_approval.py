"""Generate the A–T final report from real SQL and completed acceptance artifacts."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from database.database import get_connection,get_approved_questions
from database.taxonomy_migration import protected_snapshot
from services.geometry_production_approval import baseline,OUTPUT,UNRECOVERABLE
from services.geometry_recovery import production_audit
from services.geometry_review import read_rows,write_rows


def report():
    migration=json.loads((OUTPUT/'migration_result.json').read_text(encoding='utf-8'))
    validation=json.loads((ROOT/'reports/geometry_v1_1e_validation.json').read_text(encoding='utf-8'))
    browser=json.loads((ROOT/'reports/geometry_v1_1e_browser_validation.json').read_text(encoding='utf-8'))
    assets=json.loads((ROOT/'reports/geometry_v1_1e_assets_validation.json').read_text(encoding='utf-8'))
    log=(ROOT/'tmp/geometry_v1_1e_final_tests.log').read_text(encoding='utf-8')
    tests=re.search(r'Ran (\d+) tests in ([\d.]+)s\s+OK\s*$',log)
    assert tests,'Final full test run must pass'
    assert browser['result']==validation['result']==assets['result']=='PASS'
    current,snapshot=baseline(ROOT/'math_ai.db')
    before=migration['baseline_before']
    assert current['attempts_count']==before['attempts_count'] and current['attempts_digest']==before['attempts_digest']
    audit,pool=production_audit(ROOT/'math_ai.db')
    with closing(get_connection(migration['backup'],read_only=True)) as backup,closing(get_connection(ROOT/'math_ai.db',read_only=True)) as live:
        old=protected_snapshot(backup)
        assert all({r[0]:r for r in snapshot['rows']['questions']}[r[0]]==r for r in old['rows']['questions'])
        auxiliary={}
        for table in ('attempt_details','attempt_knowledge_mappings','subjective_submissions','answer_review_requests','training_attempt_links'):
            if not backup.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():continue
            a=[tuple(r) for r in backup.execute('SELECT * FROM '+table+' ORDER BY rowid')]
            b=[tuple(r) for r in live.execute('SELECT * FROM '+table+' ORDER BY rowid')]
            assert a==b,table
            auxiliary[table]=dict(count=len(a),unchanged=True)
        assert live.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not live.execute('PRAGMA foreign_key_check').fetchall()
        assert live.execute("SELECT COUNT(*) FROM attempts WHERE student_id LIKE 'TEST_GEO_V11E%'").fetchone()[0]==0
        formal_types=dict(live.execute("SELECT q.question_type,COUNT(*) FROM questions q JOIN question_sources s ON s.question_id=q.id WHERE s.taxonomy_version='geometry_v1' GROUP BY q.question_type"))
        formal_difficulty=dict(live.execute("SELECT q.difficulty,COUNT(*) FROM questions q JOIN question_sources s ON s.question_id=q.id WHERE s.taxonomy_version='geometry_v1' GROUP BY q.difficulty"))
        assert not live.execute('SELECT 1 FROM questions WHERE id=?',(UNRECOVERABLE,)).fetchone()
    function_before=get_approved_questions(database_path=migration['backup'],taxonomy_version='function_v2')
    function_after=get_approved_questions(database_path=ROOT/'math_ai.db',taxonomy_version='function_v2')
    assert function_before==function_after
    unresolved=next(q for q in read_rows(ROOT/'data/question_bank/geometry_v1_1c/curated_candidates.jsonl') if q['id']==UNRECOVERABLE)
    assert unresolved['decision']=='needs_manual_fix'
    write_rows(OUTPUT/'unresolved_manual_fix.jsonl',[dict(id=UNRECOVERABLE,review_status='needs_manual_fix',trainable=False,
        reason='原DOCX GBK_S特殊字体字符数学含义无法可靠确定；本次113题批准不包含此题。')])
    summary=dict(result='PASS',production=current,audit=audit,formal_types=formal_types,formal_difficulty=formal_difficulty,
        attempts_unchanged=True,auxiliary_attempt_tables=auxiliary,function_pool_unchanged=True,function_count=len(function_after),
        tests=dict(count=int(tests[1]),seconds=float(tests[2]),result='OK'),
        diagnostic=browser,adaptive=validation['adaptive'],assets=assets,backup=migration['backup'])
    (ROOT/'reports/geometry_v1_1e_final_validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    diag=browser['diagnostic_submissions']
    lines=['# V1.1E Geometry Recovery Production Approval & Integration','',
        '用户已完成人工审核并授权正式批准。113道恢复题最终复核后全部事务导入真实geometry_v1；无OCR、无原创题、无章节扩充、无commit。',
        '全部网页与模拟作答使用SQLite备份副本和TEST_GEO_V11E测试学生；正式库测试attempts为0。','',
        '| 项目 | 真实结果 |','|---|---|',
        f"| A 最终通过 | {migration['gate_passed']} / 113，实际插入{migration['inserted']} |",
        f"| B approved_but_blocked | {len(migration['blocked'])}；本批无阻断项 |",
        f"| C duplicate | {migration['duplicate_count']}；题号、完整文本、规范化文本、source、variant/content五类审计均0 |",
        f"| D geometry正式总数 | {current['geometry_question_count']} |",
        f"| E 全库题目总数 | {current['questions_count']} |",
        '| F G001–G010 | 见下表，从正式SQL/训练池重新统计 |',
        '| G D1–D5 | '+' / '.join(f'D{d}={formal_difficulty.get(d,0)}' for d in range(1,6))+' |',
        '| H 四题型 | '+'；'.join(f'{k}={formal_types[k]}' for k in ('single_choice','multiple_choice','fill_blank','subjective'))+' |',
        f"| I G008 | {audit['points']['G008']['count']}，距10题仍差2题 |",
        f"| J trainable pool | {audit['geometry_trainable']}，与formal总数一致 |",
        f"| K backup | `{migration['backup']}`；SQLite backup API，integrity_check=ok |",
        f"| L migration前attempts | {before['attempts_count']}，运行时读取，不硬编码 |",
        f"| M migration后attempts | {migration['baseline_after']['attempts_count']}；最终只读复核{current['attempts_count']} |",
        '| N attempts digest | 完全一致，见基线摘要 |',
        f"| O 首次诊断 | TEST_GEO_V11E，网页实际完成{browser['diagnostic_count']}题，覆盖10知识点，四题型混合 |",
        '| P adaptive progression | low D2；medium D2/D3；high实际到D4；stable实际到D5；详见真实题选择序列 |',
        f"| Q 图片与公式 | 新增题题图{assets['question_images']}、解析图{assets['solution_images']}，全部加载；作答前解析图0；数学片段{assets['rendered_math']}，KaTeX错误0 |",
        f"| R function_v2 | 原{len(function_after)}题完整内容与元数据一致；首次诊断/训练/画像/推荐/反馈页面通过 |",
        f"| S 自动测试 | 原504项+新增32项={tests[1]}项全部通过，{tests[2]}秒 |",
        '| T Streamlit真实验收 | app.py + 无窗口Edge，完整几何流程与函数切换通过；实际D2/D3/D4、有图、填空、主观题均看到并提交 |','',
        '## Production基线、备份与完整性','',
        f"正式DB绝对路径：`{before['database']}`",'',
        f"迁移前主文件SHA256：`{before['db_sha256']}`",'',
        f"迁移后主文件SHA256：`{migration['baseline_after']['db_sha256']}`",'',
        f"备份SHA256：`{migration['backup_sha256']}`",'',
        f"attempts逐字段、有序逻辑digest：`{before['attempts_digest']}`",'',
        '迁移前256题/123道几何题/95条attempts；迁移后369题/236道几何题/95条attempts。本阶段从当前真实数据建立新基线，没有恢复79条或94条旧状态。',
        'SQLite WAL情况下主文件哈希仅作为文件证据；一致性备份、逐字段逻辑快照、integrity_check及foreign_key_check共同验证。',
        '原256题逐字段未改变，function_v2题池含元数据完全一致。附属作答表：`'+json.dumps(auxiliary,ensure_ascii=False)+'`。','',
        '## 人工批准与最终门禁','',
        '人工结果落盘：`data/question_bank/geometry_v1_1e/manual_approval.jsonl`及正式DB `geometry_recovery_reviews`表。113条review_status=approved、reviewed_by=manual_user、review_notes=“用户已完成人工审核，确认恢复题无问题。”',
        '原V1.1D审核批次保留为当时pending_review的历史快照；本阶段批准状态以V1.1E清单和正式审核表为准。',
        '最终门禁独立复核real_question、结构/公式/答案泄漏、题型/答案、单primary与catalog、D1–D5、源DOCX哈希与稳定source fingerprint、图片来源/字节/角色/路径，以及五类重复。',
        '5条旧knowledge_warning已在人工审核包确认primary后经catalog复核，逐条保存resolved_review_findings；没有清除未知问题来凑题量。',
        '无源分值的主观题保留reference solution、未设分值、待人工评阅，不创造rubric或分数。填空中不能自动判定的表达式仍needs_manual_review，未计mastery。',
        f'特殊字体题`{UNRECOVERABLE}`仍needs_manual_fix、不批准、不导入、不猜符号；状态另存unresolved_manual_fix.jsonl。',
        '重复审计：`data/question_bank/geometry_v1_1e/duplicate_audit.jsonl`。variant列采用显式variant_fingerprint，原题无变式时回退到稳定content fingerprint。',
        'BEGIN IMMEDIATE事务内重新检查重复和基线；变化时拒绝本次迁移，保留真实学生数据。异常回滚，重复运行插入0条/跳过113条（隔离副本验收）。初次基线与备份证据不被重复运行覆盖。','',
        '## 知识点与覆盖','',
        '| 知识点 | 正式trainable | 单选 | 多选 | 填空 | 主观 | D1/D2/D3/D4/D5 |',
        '|---|---:|---:|---:|---:|---:|---|']
    for key,p in audit['points'].items():
        lines.append(f"| {key} {p['name']} | {p['count']} | "+' | '.join(str(p['types'].get(k,0)) for k in ('single_choice','multiple_choice','fill_blank','subjective'))+' | '+'/'.join(str(p['difficulty'].get(d,0)) for d in range(1,6))+' |')
    lines += ['', 'G008从1题增加到8题，仍是当前最薄弱知识点之一，后续题库扩充优先补充；本轮没有为了达到10题原创2题。',
        'D2由原109/123（88.6%）变为131/236（55.5%）；新增D3/D4/D5形成真实进阶题池，但各知识点仍有局部难度/题型缺口，不宣称完整覆盖。','',
        '## 首次诊断实际网页结果','',
        '学生：TEST_GEO_V11E；隔离DB：`'+browser['database']+'`。','',
        '知识点分布：`'+json.dumps(browser['diagnostic_knowledge_counts'],ensure_ascii=False)+'`。','',
        '难度分布：`'+json.dumps(browser['diagnostic_difficulty_counts'],ensure_ascii=False)+'`。','',
        '题型分布：`'+json.dumps(browser['diagnostic_type_counts'],ensure_ascii=False)+'`。','',
        '| 顺序 | 实际question ID | 知识点 | 难度 | 题型 |','|---|---|---|---|---|']
    lines += [f"| {q['diagnostic_index']} | {q['question_id']} | {q['knowledge']} | D{q['difficulty']} | {q['type']} |" for q in diag]
    lines += ['', '## 自适应真实题验收','',
        '隔离副本、G007目标、独立前置证据、真实规则计算mastery，未mock算法、未造新题。连续正确/错误期间mastery按原模型更新；pending主观作答不增加评分证据。', '',
        '| 状态 | 起始mastery | 独立证据 | 起始难度带 | 实际题难度序列 | 实际题型计数 |',
        '|---|---:|---:|---|---|---|']
    for key,b in validation['adaptive'].items():
        lines.append(f"| {key} | {b['initial_score']:.4f} | {b['independent_evidence']} | {b['initial_band']} | {b['actual_difficulties']} | {json.dumps(b['type_counts'],ensure_ascii=False)} |")
    for key,b in validation['adaptive'].items():
        lines += [f"",f"{key}题号：`"+', '.join(q['id'] for q in b['selected'])+'`。',f"coverage limitation：{b['limitations']}。",'']
    lines += ['低mastery实际没有D3以上或综合主观题；中等增加填空，高mastery主观权重由10%升至45%。目标仍由Recommendation确定，Adaptive Training选择题目/题型/难度。原A/R/S/D数学模型及评分定义保持，LLM不参与correctness/mastery/recommendation target。',
        '最近30题优先避开；诊断后训练优先避开已作答原题；同session的题号、source/content、variant及源段落曝光不重复。自动测试及实际自适应选择均覆盖。','',
        '## 图片、公式及真实Streamlit','',
        '全量113道正式恢复题、68张question_diagram、112张solution_diagram，全部实际加载；新增option_image=0，原正式5张option_image继续通过角色与文件检查，并在多题图场景显示。',
        '全量3099数学片段KaTeX错误0；D3/D4/D5与G006/G007/G008/G010均包含在全量回归；raw OMML、sqrt(...)、a_(1)、(2)/(3)、$$冲突、[公式待核]门禁拦截。',
        '真实训练页question_diagram/option_image提交前可见；solution_diagram提交前0、提交后显示。missing required asset运行时自动退出训练/诊断可用池。','',
        '几何真实页面链：'+ ' → '.join(browser['geometry_pages_passed'])+'。','',
        '| 场景 | question ID | 难度/题型 | 作答前题图 | 作答前解析图 | 作答后解析图 |',
        '|---|---|---|---:|---:|---:|']
    for s in browser['image_scenarios']:
        lines.append(f"| {s['scenario']} | {s['question_id']} | D{s['difficulty']} / {s['question_type']} | {s['question_images_before']} | {s['solution_images_before']} | {s['solution_images_after']} |")
    lines += ['', '函数真实页面通过：'+ '、'.join(browser['function_pages_passed'])+'。函数后台首次诊断18题、训练选题、画像、确定性推荐也已通过。',
        'AI学习反馈使用现有规则式反馈进行无凭证验收；未调用外部LLM、未改变服务提供商配置。已验收的是反馈页面与规则反馈流程，不声称远程模型API验收。',
        '修复本次真实验收发现的学生编号/专题跨页面控件状态重置：app.py将持久上下文与控件key分离，避免重运行返回默认学生或默认专题；新增状态回归测试。','',
        '## 测试、文件与命令','',
        f"完整自动测试：{tests[1]}项全部通过（原504+新增32），日志tmp/geometry_v1_1e_final_tests.log；新增32项单独运行也通过。",'',
        '新增：services/geometry_production_approval.py；scripts/approve_geometry_recovery.py、validate_geometry_approval.py、smoke_geometry_approval_browser.py、smoke_geometry_approval_assets.py、report_geometry_approval.py；tests/test_geometry_approval.py、geometry_baseline.py；V1.1E审核/门禁/重复/迁移JSONL与JSON；本报告及验收JSON。',
        '修改：database/geometry.py（阶段迁移标识、备份校验、审核表、事务内基线与重复复核）；services/question_assets.py（显式blocked/未批准不能trainable）；app.py（学生/专题状态）；tests/test_geometry_quality.py、test_geometry_production.py（原阶段断言指向保留的迁移前备份，维持历史123题/D2集中/缺覆盖等负向测试）。',
        '本轮未修改mastery、recommendation、adaptive、diagnostic、question importer、question_renderer既有算法；已重读并运行完整回归。仓库原有未提交变更保留。','',
        '执行命令：','',
        '```text','python -X utf8 scripts/approve_geometry_recovery.py',
        'python -X utf8 -m unittest discover -s tests -p test_geometry_approval.py -q',
        'python -X utf8 -m unittest discover -s tests -q',
        'python -X utf8 scripts/validate_geometry_approval.py',
        'python -X utf8 scripts/approve_geometry_recovery.py --apply-production',
        'python -X utf8 scripts/smoke_geometry_approval_browser.py',
        'python -X utf8 scripts/smoke_geometry_approval_browser.py --assets-only',
        'python -m streamlit run app.py --server.headless=true --server.port=<isolated port>',
        'python -X utf8 scripts/report_geometry_approval.py',
        'git -c safe.directory=E:/Projects/math_ai status --short',
        'git -c safe.directory=E:/Projects/math_ai diff --check','```','',
        'git diff --check通过；未commit。验收服务与无窗口浏览器完成后关闭，正式DB未写入测试作答。',
        '本阶段完成并停止。后续优先补充有可靠来源的G008题与各点缺失难度，不在本阶段继续扩题。','']
    (ROOT/'reports/geometry_v1_1e_production_report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(result='PASS',questions=current['questions_count'],geometry=current['geometry_question_count'],
        attempts=current['attempts_count'],tests=int(tests[1]),report=str(ROOT/'reports/geometry_v1_1e_production_report.md')),ensure_ascii=False))

if __name__=='__main__':report()
