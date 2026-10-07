# V1.0D 多题型训练基础

## V1.0D.2 正式接入

用户明确审核的 batch_001 现已批准并导入：20道多选、25道填空、16道主观题。正式库共有133道题（72/20/25/16）；原66道新增单选和6道种子题全部保留。batch_002 未批准、未导入。原 candidates 未改写，三个 approved JSONL 与 manual_user 审计分别保存在 data/question_bank/approved/ 和 data/question_bank/reviews/。

`python scripts/approve_multitype_batches.py` 用于重建已有明确用户审核结果，不能用于任意未审题。批准前复检 validator 并核验运行时小问包装；任何失败题单独阻止批准并列入报告。运行时只添加 canonical_answer 别名、小问 ID 与原评分点引用，保留已审核题干、答案、评分点文字和分值；approved 指纹保持与候选一致。

`python scripts/integrate_multitype_production.py --apply-production` 已执行一次正式接入。SQLite backup API 在任何 schema/题目写入前创建一致性备份，记录 questions count、attempts count/digest；随后升级并事务导入，外键检查通过。重复导入61道均 skipped。原33条 attempts 全字段摘要不变，旧题和 function_v1 查询不变。具体备份位置与摘要见 reports/v1_0d_2_production_validation.json。无需再次初始化数据库。

database/training_review.py 新增 subjective_submissions：student_id、question_id、唯一 attempt_id、text_answer、attachment_path、status、submitted_at、score、max_score、review_source。未评分提交的 status=submitted_pending_review、score=NULL、attempt.is_correct=NULL。没有新增正式评分端或 OCR。图片沿用现有 attachments/ 安全目录，随机文件名，只保存引用；大小上限10MB，校验实际格式与像素尺寸。支持PNG/JPEG，保留既有WEBP兼容。

无法安全解析的填空答案保存为 NULL correctness、pending details，并在 answer_review_requests 记录 needs_manual_review 与原因。页面允许继续下一题，不自动判错。标准答案仍由受限 SymPy/规则 evaluator 判定，支持 numeric/expression/interval/set/text 与中文区间、分数、^、sqrt、pi、inf。不受支持的集合描述或不同定义域限制转人工审核。任何 pending details（即使误写非空 is_correct）都不能进入 mastery 证据。

renderer 统一展示题目、小问、总分、输入与反馈。单选使用 radio，多选使用 multiselect，填空没有选项，大题为文本与图片上传；不预先显示标准解答。多选集合完全相等得1，否则0，顺序无关。训练结束显示题型分布、已评分正确率、待评阅大题与待人工审核填空数。画像区分有效证据和待评阅作答；反馈上下文只添加待评数量，不让模型评分。

题型比例：未评估或<40%，选择类80%/填空20%；40–70%，选择类60%/填空40%；70–85%，选择类40%/填空60%；≥85%，选择类25%/填空50%/大题25%。单选与多选共享选择类份额。有缺题时回退可用题型，前置与安全难度仍优先。按题号、来源指纹、变式指纹和原文段落曝光回避同一原题，首次未做/未见题优先。

测试：`python -m unittest discover -s tests -q`。验收浏览器脚本 `python scripts/smoke_multitype_browser.py` 使用本地 Edge、现有 websocket-client 和临时 Streamlit 服务，只操作数据库副本及合成图片。打开入口首页初始化 st.navigation，再通过导航进入训练。不会向生产库写入验收作答。

backups/、tmp/、attachments/、student_submissions/、data/student_submissions/、.env 均忽略提交。本阶段不commit，不开始 OCR 或后续版本。

## V1.0D.1 本地多题型扩充

四种正式题型为 single_choice、multiple_choice、fill_blank、subjective。多选题使用 options 与 correct_answers 列表，不使用单值 answer；学生提交集合与正确集合完全相等才判对，不计部分分。训练使用多选控件并将集合保存为 JSON 文本，原单选作答仍保存字母。

填空新增 canonical_answer 与 set 类型。有限实数集合忽略顺序与重复元素，支持集合内分数/小数等价；复杂集合描述不猜测。numeric 精确判分，expression 支持基础代数等价；涉及不同定义域限制时返回 needs_manual_review。evaluate_answer_result 提供结构化状态，训练遇到不受支持的语法时提示人工审核且不写入错误 attempt。

大题保存 sub_questions（id、stem、max_score）、reference_answers_by_subquestion 和引用小问的 rubric。小问分值、对应评分点总分均校验。rubric_source=derived_for_system 表示按原解答拆出的系统草案，不能当作官方评分细则。主观题只保存文本/图片，不调用 OCR 或自动评分，pending 不计入 mastery。

本轮重新扫描15份 DOCX，生成20道多选、35道填空、14道解答题，共69道 reviewed。为避免覆盖旧文件，填空与解答题使用 batch_002，多选使用 batch_001。重新扫描包含22道旧待审填空来源与14道旧待审解答来源；它们的本轮结构得到补充，但不是正式新增 approved。本轮与 Batch001–003 已批准单选题没有重复。候选与 review_required 文件内容一致，三份普通 Word 位于 reports/；原数学公式保留原生 OMML。

覆盖统计、难度与长期缺口见 reports/function_multitype_question_bank_report.md。风险审计采用独立可重叠计数，同时另列互斥 extraction_status，不能将两组数字直接相加。

database/four_type.py 的 schema 升级只允许显式隔离库，本轮未迁移真实库。questions 支持 multiple_choice，question_details 支持 set；question_type_extensions 用 JSON 保存多选答案与大题小问元数据。迁移保留既有问题、作答、触发器和外键关系，重复执行不改数据。正式启用需要后续用户授权的迁移/激活阶段。

题型比例中的选择题份额由单选/多选共享；没有多选题时保留原比例。选题首先考虑从未作答或曝光的题，再考虑近期30题之外的题。未提交的选择、填空、大题曝光均进入回避历史，现有变式机制继续保留。

复验命令：`python -m unittest discover -s tests -q`。隔离库验收命令：`python scripts/validate_multitype_expansion.py`。提取脚本 `python scripts/expand_multitype_question_bank.py` 拒绝覆盖已存在的审核输出；不要删除旧文件以强行重跑。

仅覆盖函数模块，保持原 mastery 和 recommendation 的确定性模型；不调用 LLM 判分、不联网、不实现 OCR 或教师端。

## 数据库与兼容

`python scripts/migrate_multi_type.py` 幂等迁移 V1.0B/V1.0C 库；训练页和新 session 也会初始化。迁移在一个事务内重建 questions、attempts 的约束，保留全部原列、原 ID、原值、索引、关联及自增序列，并在提交前检查历史行与外键。新版题目保存在现有 questions，旧单选题仍为 single_choice。

| 结构 | 字段与语义 |
| --- | --- |
| questions | question_type 为 single_choice / fill_blank / subjective；非单选题 options、answer 为 NULL，不创建 A/B/C/D |
| question_details | answer_expression、accepted_answers（JSON）、answer_type；reference_answer、solution_steps（JSON）、rubric（JSON）、max_score |
| attempts | user_answer 保存选项或原始文本；主观题未评分时 is_correct=NULL，区别于错误的 0 |
| attempt_details | question_type、answer_payload（JSON）、attachment_path、scoring_status、score、max_score；主观题 pending，客观题 scored |

保留旧记录不追填新元数据；旧记录按关联题目默认为单选题。新作答在同一事务中写入 attempts、attempt_details、training_attempt_links 和 session。

## 判分范围

`services/answer_evaluator.py` 的 evaluate_fill_blank 返回 bool；不支持的语法抛 ValueError，页面提示修改，不记录成错误证据。

- numeric：精确实数等价，1/2 与 0.5 等价；不使用未声明的小数误差容忍度。
- expression：有限的普通数学表达式，支持 x^2-1、(x-1)(x+1)、sqrt、abs、ln 等；通过受限 AST 构造 SymPy 对象，禁止 eval、任意属性或函数调用。仅作基础代数等价判断，不推断表达式的定义域；有定义域要求的答案需独立设置区间题。
- interval：开闭端点、实数端点、±∞、区间并集。支持中文逗号/括号，以及分数端点；无穷端点不能闭合。暂不支持一般集合描述或任意不等式字符串。
- text：Unicode 规范化、去除首尾空格后的明确文本匹配，不由 LLM 推断语义。

accepted_answers 提供多种允许答案，answer_expression 提供标准表达式。判分依据经人工批准的题目元数据，不使用模型生成的标准答案。

## 主观题与图片

主观题保存文本与可选 PNG/JPEG/WEBP 图片，允许只上传图片。验证图片格式、大小、尺寸后，以随机文件名保存在数据库同目录的 attachments/；SQLite 只保存路径与文本 JSON。附件目录在 .gitignore 中，禁止提交学生作答图片。

当前不自动 OCR，也不自动评分。页面显示“主观题自动识别与评分功能将在后续版本完善。”未评分主观题不触发连续正确/错误决策，不计入 mastery 的作答数或正确率；训练结束报告分别展示总提交数、已评分数、待评分数。mastery 查询还检查主观题 scoring_status=scored，避免仅写入非空 is_correct 就污染学情。

没有新增人工评分页面。以后人工/规则评分必须先完成审核、填写评分状态与结果，再允许作为学情证据。

## UI 与题型比例

`services/question_renderer.py` 提供统一 render_answer_input/read_answer_input/render_saved_answer。训练页依题型切换 radio、单行文本输入或多行文本加图片上传，提交、提示、下一题及会话恢复共用流程。

| 当前目标掌握度 | single_choice | fill_blank | subjective |
| --- | ---: | ---: | ---: |
| 未评估或 <60% | 60% | 40% | 0% |
| 60%–80% | 40% | 60% | 0% |
| ≥80% | 25% | 50% | 25% |

按比例缺口确定下一题型，有题库不足时回退；不是随机抽样或强制精确配额。近期30题、同轮不重复、前置知识与难度安全门槛仍优先。题库只有单选题时保持兼容；首次诊断页本阶段继续使用原单选流程。

## 导入与本地提取

question_validator 分题型校验：单选选项完整且不同，答案为 A/B/C/D；填空有可判分的标准答案/接受答案和 answer_type；主观有参考解答、解答步骤、结构化 rubric，其正分值合计等于 max_score。

原 import_questions 支持三类题目 JSON，仍只允许 approved 进入隔离题库；新增 activate_training_questions 是显式 approved-only 训练适配器，不由提取脚本自动调用。向真实库激活还要求调用者提供明确授权标志。本批 reviewed 候选没有导入训练。

扫描现有15份本地 DOCX，首批输出25道填空、16道主观题。优先完整、无图片依赖、标准答案与解答明确的题；多空映射、开放性填空、缺图、公式警告及未入选候选记录在 reports/multi_type_extraction_audit.json。主观评分点沿用原分问分值；未标分时提供明确标记的草案。3道独立小问保留 source_subquestion 与不连续的 source_ranges，不继承其他小问条件。全部 reviewed、annotation_status=pending_review，尚未数学或许可批准。

可读版复制选定原文段落和原生 Word 数学公式，方便核对题干、答案及评分草案。来源保留文件、段落定位和 SHA-256；不猜测页码，不声称许可已明确。脚本拒绝覆盖已有候选快照。

## 未来 OCR 流程

image → math OCR → LaTeX → **学生确认识别结果** → evaluator → rubric scorer

`services/handwriting_recognition.py:recognize_math_image(image_path)` 当前只返回 status=not_implemented，不调用任何第三方服务。学生确认识别结果是未来必须保留的环节。识别模型输出不能直接成为评分依据。

## 验证

运行 `python -m unittest discover -s tests -q`。新测试使用临时 SQLite、离线 SymPy、内存测试图片和 Streamlit AppTest，不需要 API 凭据或网络。

正式库仅迁移结构；人工批准本批候选前，真实页面仍会使用现有已批准单选题。三种 UI、主观图片引用和未评分门槛已在隔离测试库验证。
