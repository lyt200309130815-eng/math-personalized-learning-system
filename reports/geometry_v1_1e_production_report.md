# V1.1E Geometry Recovery Production Approval & Integration

用户已完成人工审核并授权正式批准。113道恢复题最终复核后全部事务导入真实geometry_v1；无OCR、无原创题、无章节扩充、无commit。
全部网页与模拟作答使用SQLite备份副本和TEST_GEO_V11E测试学生；正式库测试attempts为0。

| 项目 | 真实结果 |
|---|---|
| A 最终通过 | 113 / 113，实际插入113 |
| B approved_but_blocked | 0；本批无阻断项 |
| C duplicate | 0；题号、完整文本、规范化文本、source、variant/content五类审计均0 |
| D geometry正式总数 | 236 |
| E 全库题目总数 | 369 |
| F G001–G010 | 见下表，从正式SQL/训练池重新统计 |
| G D1–D5 | D1=4 / D2=131 / D3=74 / D4=23 / D5=4 |
| H 四题型 | single_choice=104；multiple_choice=37；fill_blank=51；subjective=44 |
| I G008 | 8，距10题仍差2题 |
| J trainable pool | 236，与formal总数一致 |
| K backup | `E:\Projects\math_ai\backups\math_ai_pre_geometry_v1_1e_20261009T101133500979Z.db`；SQLite backup API，integrity_check=ok |
| L migration前attempts | 95，运行时读取，不硬编码 |
| M migration后attempts | 95；最终只读复核95 |
| N attempts digest | 完全一致，见基线摘要 |
| O 首次诊断 | TEST_GEO_V11E，网页实际完成15题，覆盖10知识点，四题型混合 |
| P adaptive progression | low D2；medium D2/D3；high实际到D4；stable实际到D5；详见真实题选择序列 |
| Q 图片与公式 | 新增题题图68、解析图112，全部加载；作答前解析图0；数学片段3099，KaTeX错误0 |
| R function_v2 | 原128题完整内容与元数据一致；首次诊断/训练/画像/推荐/反馈页面通过 |
| S 自动测试 | 原504项+新增32项=536项全部通过，111.121秒 |
| T Streamlit真实验收 | app.py + 无窗口Edge，完整几何流程与函数切换通过；实际D2/D3/D4、有图、填空、主观题均看到并提交 |

## Production基线、备份与完整性

正式DB绝对路径：`E:\Projects\math_ai\math_ai.db`

迁移前主文件SHA256：`c68f1dac8bc6e47a0d002dde29bc00ea60adefb3794f36e53fe88b4d300c524e`

迁移后主文件SHA256：`287393040d1277638c7ccd39a4a64363b2ab58a0e6ed778ef4f1f9d2cf2f5f57`

备份SHA256：`149ce796c6c2ffe1db4c58ac21581368b0251ca4ba99cec6555124cd85ab237c`

attempts逐字段、有序逻辑digest：`6c0277fa573841863b2c8db37724302a057a35cb4e0c2b50e7be71077bf6b1bc`

迁移前256题/123道几何题/95条attempts；迁移后369题/236道几何题/95条attempts。本阶段从当前真实数据建立新基线，没有恢复79条或94条旧状态。
SQLite WAL情况下主文件哈希仅作为文件证据；一致性备份、逐字段逻辑快照、integrity_check及foreign_key_check共同验证。
原256题逐字段未改变，function_v2题池含元数据完全一致。附属作答表：`{"attempt_details": {"count": 58, "unchanged": true}, "subjective_submissions": {"count": 6, "unchanged": true}, "answer_review_requests": {"count": 6, "unchanged": true}, "training_attempt_links": {"count": 10, "unchanged": true}}`。

## 人工批准与最终门禁

人工结果落盘：`data/question_bank/geometry_v1_1e/manual_approval.jsonl`及正式DB `geometry_recovery_reviews`表。113条review_status=approved、reviewed_by=manual_user、review_notes=“用户已完成人工审核，确认恢复题无问题。”
原V1.1D审核批次保留为当时pending_review的历史快照；本阶段批准状态以V1.1E清单和正式审核表为准。
最终门禁独立复核real_question、结构/公式/答案泄漏、题型/答案、单primary与catalog、D1–D5、源DOCX哈希与稳定source fingerprint、图片来源/字节/角色/路径，以及五类重复。
5条旧knowledge_warning已在人工审核包确认primary后经catalog复核，逐条保存resolved_review_findings；没有清除未知问题来凑题量。
无源分值的主观题保留reference solution、未设分值、待人工评阅，不创造rubric或分数。填空中不能自动判定的表达式仍needs_manual_review，未计mastery。
特殊字体题`GQ-50a2466ead939ff28bd5`仍needs_manual_fix、不批准、不导入、不猜符号；状态另存unresolved_manual_fix.jsonl。
重复审计：`data/question_bank/geometry_v1_1e/duplicate_audit.jsonl`。variant列采用显式variant_fingerprint，原题无变式时回退到稳定content fingerprint。
BEGIN IMMEDIATE事务内重新检查重复和基线；变化时拒绝本次迁移，保留真实学生数据。异常回滚，重复运行插入0条/跳过113条（隔离副本验收）。初次基线与备份证据不被重复运行覆盖。

## 知识点与覆盖

| 知识点 | 正式trainable | 单选 | 多选 | 填空 | 主观 | D1/D2/D3/D4/D5 |
|---|---:|---:|---:|---:|---:|---|
| G001 基本立体图形与表面积体积 | 36 | 21 | 5 | 8 | 2 | 2/22/11/1/0 |
| G002 球的切接问题 | 22 | 14 | 2 | 6 | 0 | 0/17/5/0/0 |
| G003 空间点线面位置关系 | 27 | 14 | 4 | 5 | 4 | 0/18/9/0/0 |
| G004 空间直线、平面的平行 | 27 | 10 | 3 | 4 | 10 | 0/15/9/3/0 |
| G005 空间直线、平面的垂直 | 27 | 8 | 7 | 6 | 6 | 0/16/10/1/0 |
| G006 空间向量概念与运算 | 27 | 12 | 4 | 7 | 4 | 1/14/8/4/0 |
| G007 向量法求空间角 | 30 | 9 | 2 | 7 | 12 | 0/8/9/10/3 |
| G008 空间距离 | 8 | 3 | 1 | 2 | 2 | 0/1/5/2/0 |
| G009 截面与交线问题 | 17 | 6 | 5 | 3 | 3 | 1/12/2/2/0 |
| G010 动态与轨迹问题 | 15 | 7 | 4 | 3 | 1 | 0/8/6/0/1 |

G008从1题增加到8题，仍是当前最薄弱知识点之一，后续题库扩充优先补充；本轮没有为了达到10题原创2题。
D2由原109/123（88.6%）变为131/236（55.5%）；新增D3/D4/D5形成真实进阶题池，但各知识点仍有局部难度/题型缺口，不宣称完整覆盖。

## 首次诊断实际网页结果

学生：TEST_GEO_V11E；隔离DB：`E:\Projects\math_ai\tmp\geometry_v1_1e_browser_20261009T103004452350Z\browser.sqlite3`。

知识点分布：`{"G001": 2, "G003": 2, "G005": 2, "G006": 2, "G002": 1, "G004": 1, "G007": 1, "G009": 2, "G008": 1, "G010": 1}`。

难度分布：`{"1": 4, "2": 9, "3": 2}`。

题型分布：`{"single_choice": 5, "fill_blank": 6, "multiple_choice": 2, "subjective": 2}`。

| 顺序 | 实际question ID | 知识点 | 难度 | 题型 |
|---|---|---|---|---|
| 1 | GQ-aeab0d608dce8a27152f | G001 | D1 | single_choice |
| 2 | GQ-002b3baad92884d4f8e5 | G003 | D2 | fill_blank |
| 3 | GQ-bf51ca20127ed8c85b25 | G001 | D1 | multiple_choice |
| 4 | GQ-1db6c10b3f448db73138 | G003 | D2 | single_choice |
| 5 | GQ-12278a7ed57a2af16f77 | G005 | D3 | subjective |
| 6 | GQ-746dbc126dec6096e365 | G006 | D1 | fill_blank |
| 7 | GQ-148ebe88f26537ba5829 | G002 | D2 | single_choice |
| 8 | GQ-11fc0a419a885602540f | G004 | D2 | single_choice |
| 9 | GQ-91a88f8dfb1d7a8be94d | G007 | D2 | fill_blank |
| 10 | GQ-a3da059167dc643a126b | G009 | D1 | multiple_choice |
| 11 | GQ-ddfae3124c26a1e4e165 | G008 | D2 | fill_blank |
| 12 | GQ-31d1653825585036a8aa | G010 | D2 | fill_blank |
| 13 | GQ-02d8239d414229002960 | G005 | D2 | single_choice |
| 14 | GQ-04596702baf31dee43a0 | G006 | D2 | fill_blank |
| 15 | GQ-02c40d2a9ed597ab3b4b | G009 | D3 | subjective |

## 自适应真实题验收

隔离副本、G007目标、独立前置证据、真实规则计算mastery，未mock算法、未造新题。连续正确/错误期间mastery按原模型更新；pending主观作答不增加评分证据。

| 状态 | 起始mastery | 独立证据 | 起始难度带 | 实际题难度序列 | 实际题型计数 |
|---|---:|---:|---|---|---|
| low | 0.0000 | 6 | [1, 2] | [2, 2] | {"multiple_choice": 1, "fill_blank": 1} |
| medium | 0.5992 | 6 | [2, 3] | [2, 3, 3, 2] | {"fill_blank": 1, "subjective": 1, "single_choice": 1, "multiple_choice": 1} |
| high | 0.8917 | 6 | [3, 4] | [3, 3, 5, 5, 4] | {"subjective": 2, "fill_blank": 2, "single_choice": 1} |
| stable | 1.0000 | 6 | [4, 5] | [4, 4, 5, 5, 4] | {"subjective": 2, "fill_blank": 2, "single_choice": 1} |

low题号：`GQ-d072168a6a2b4618193b, GQ-a3c56f8e34d9499c8d4e`。
coverage limitation：['题库覆盖不足（coverage limitation）：当前目标缺少D1，不能验证相应难度的进阶表现。']。


medium题号：`GQ-a3c56f8e34d9499c8d4e, GQ-4fb6af5b58bb045b1748, GQ-155681ce367440fbbbfd, GQ-d072168a6a2b4618193b`。
coverage limitation：['题库覆盖不足（coverage limitation）：当前目标缺少D1，不能验证相应难度的进阶表现。']。


high题号：`GQ-4fb6af5b58bb045b1748, GQ-31a0b5b4e45a5aecee2c, GQ-94718acd9705ca42a24c, GQ-b77331da505f430251e7, GQ-e40e37a44adefbaa9e88`。
coverage limitation：[]。


stable题号：`GQ-1e1dd34177287bb91ad8, GQ-e40e37a44adefbaa9e88, GQ-94718acd9705ca42a24c, GQ-b77331da505f430251e7, GQ-e8c0fda7221b1d2f6f0b`。
coverage limitation：[]。

低mastery实际没有D3以上或综合主观题；中等增加填空，高mastery主观权重由10%升至45%。目标仍由Recommendation确定，Adaptive Training选择题目/题型/难度。原A/R/S/D数学模型及评分定义保持，LLM不参与correctness/mastery/recommendation target。
最近30题优先避开；诊断后训练优先避开已作答原题；同session的题号、source/content、variant及源段落曝光不重复。自动测试及实际自适应选择均覆盖。

## 图片、公式及真实Streamlit

全量113道正式恢复题、68张question_diagram、112张solution_diagram，全部实际加载；新增option_image=0，原正式5张option_image继续通过角色与文件检查，并在多题图场景显示。
全量3099数学片段KaTeX错误0；D3/D4/D5与G006/G007/G008/G010均包含在全量回归；raw OMML、sqrt(...)、a_(1)、(2)/(3)、$$冲突、[公式待核]门禁拦截。
真实训练页question_diagram/option_image提交前可见；solution_diagram提交前0、提交后显示。missing required asset运行时自动退出训练/诊断可用池。

几何真实页面链：学习画像 → 个性化推荐 → 推荐进入训练 → AI 学习反馈（规则式）。

| 场景 | question ID | 难度/题型 | 作答前题图 | 作答前解析图 | 作答后解析图 |
|---|---|---|---:|---:|---:|
| no_diagram_choice | GQ-06a36c33278d4f63f79d | D2 / single_choice | 0 | 0 | 0 |
| diagram_choice | GQ-02d8239d414229002960 | D2 / single_choice | 1 | 0 | 0 |
| fill_blank | GQ-002b3baad92884d4f8e5 | D2 / fill_blank | 0 | 0 | 0 |
| subjective | GQ-05d7b75071ca37a7e8ad | D4 / subjective | 1 | 0 | 1 |
| d3 | GQ-094f702eaedcaa200984 | D3 / fill_blank | 0 | 0 | 1 |
| d4 | GQ-05d7b75071ca37a7e8ad | D4 / subjective | 1 | 0 | 1 |
| multi_diagram | GQ-1db6c10b3f448db73138 | D2 / single_choice | 2 | 0 | 2 |
| solution_only | GQ-02c40d2a9ed597ab3b4b | D3 / subjective | 0 | 0 | 1 |

函数真实页面通过：首次诊断、开始训练、学习画像、个性化推荐、AI 学习反馈。函数后台首次诊断18题、训练选题、画像、确定性推荐也已通过。
AI学习反馈使用现有规则式反馈进行无凭证验收；未调用外部LLM、未改变服务提供商配置。已验收的是反馈页面与规则反馈流程，不声称远程模型API验收。
修复本次真实验收发现的学生编号/专题跨页面控件状态重置：app.py将持久上下文与控件key分离，避免重运行返回默认学生或默认专题；新增状态回归测试。

## 测试、文件与命令

完整自动测试：536项全部通过（原504+新增32），日志tmp/geometry_v1_1e_final_tests.log；新增32项单独运行也通过。

新增：services/geometry_production_approval.py；scripts/approve_geometry_recovery.py、validate_geometry_approval.py、smoke_geometry_approval_browser.py、smoke_geometry_approval_assets.py、report_geometry_approval.py；tests/test_geometry_approval.py、geometry_baseline.py；V1.1E审核/门禁/重复/迁移JSONL与JSON；本报告及验收JSON。
修改：database/geometry.py（阶段迁移标识、备份校验、审核表、事务内基线与重复复核）；services/question_assets.py（显式blocked/未批准不能trainable）；app.py（学生/专题状态）；tests/test_geometry_quality.py、test_geometry_production.py（原阶段断言指向保留的迁移前备份，维持历史123题/D2集中/缺覆盖等负向测试）。
本轮未修改mastery、recommendation、adaptive、diagnostic、question importer、question_renderer既有算法；已重读并运行完整回归。仓库原有未提交变更保留。

执行命令：

```text
python -X utf8 scripts/approve_geometry_recovery.py
python -X utf8 -m unittest discover -s tests -p test_geometry_approval.py -q
python -X utf8 -m unittest discover -s tests -q
python -X utf8 scripts/validate_geometry_approval.py
python -X utf8 scripts/approve_geometry_recovery.py --apply-production
python -X utf8 scripts/smoke_geometry_approval_browser.py
python -X utf8 scripts/smoke_geometry_approval_browser.py --assets-only
python -m streamlit run app.py --server.headless=true --server.port=<isolated port>
python -X utf8 scripts/report_geometry_approval.py
git -c safe.directory=E:/Projects/math_ai status --short
git -c safe.directory=E:/Projects/math_ai diff --check
```

git diff --check通过；未commit。验收服务与无窗口浏览器完成后关闭，正式DB未写入测试作答。
本阶段完成并停止。后续优先补充有可靠来源的G008题与各点缺失难度，不在本阶段继续扩题。
