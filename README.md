# 高中数学个性化 AI 训练系统

教师主导、AI 辅助的数学训练项目。当前完成 V0.1–V0.7，覆盖函数模块 K001–K005。掌握度和推荐使用确定性规则；AI 仅解释已有结果，尚未实现自动学习计划。

已实现：SQLite 数据基础、高中函数题库、Streamlit 学生训练、学习行为采集、知识掌握度分析、学生知识画像、个性化学习推荐和 AI 个性化学习反馈。

## 环境与运行

使用 Python 3.10 或更新版本。V0.1 使用标准库，V0.2 需要 Streamlit。

```powershell
python -m pip install -r requirements.txt
python init_db.py
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

初始化在项目根目录生成 `math_ai.db`，不受运行时工作目录影响。可以重复执行：仅插入缺失的固定 ID 种子数据，不覆盖已有题目、知识点或学生记录。种子内容变更不会自动更新现有数据库。

## 文件职责

- `app.py`：应用入口，默认进入函数训练。
- `pages/training.py`：中文题目、单选、提交反馈和下一题。
- `pages/profile.py`：只读知识画像、总体概览、横向条形图和详细指标。
- `services/training.py`：会话状态、单调时钟计时和防重复提交逻辑。
- `services/mastery.py`：可解释的确定性掌握度计算，不写入数据库。
- `services/profile.py`：现有掌握度结果的显示格式与概览汇总，不重算掌握度。
- `services/recommendation.py`：前置知识回退、证据量策略、难度匹配及近期题目去重。
- `pages/recommendation.py`：个性化训练推荐与题目只读预览。
- `services/feedback.py`：最小学情上下文、Responses API 调用和规则式降级反馈。
- `pages/feedback.py`：确定性摘要、按需生成按钮及会话反馈缓存。
- `database/database.py`：统一连接，启用外键，返回 `sqlite3.Row`；调用者负责关闭连接。
- `init_db.py`：事务内创建三张表，初始化知识点并导入题库。
- `data/questions.csv`：六道函数单选题及答案、解析。
- `tests/test_database.py`：使用临时数据库的离线自动测试。
- `tests/test_training.py`：题库读取、JSON 校验及 Streamlit 交互测试。
- `tests/test_attempts.py`：作答持久化、最近记录查询和计时、防重复提交测试。
- `tests/test_mastery.py`：临时数据库中的指标、等级边界、证据量及只读计算测试。
- `tests/test_profile.py`：画像格式、未评估处理、最新数据读取及页面导航测试。
- `tests/test_recommendation.py`：临时数据库中的推荐规则、题目选择及页面测试。
- `tests/test_feedback.py`：mock SDK、输入保护、错误降级和请求次数测试。

## 函数训练

页面从 SQLite 查询题目及知识点名称，按题目 ID 排序，不直接读取 CSV。初始无选中答案，提交后显示对错、正确答案、知识点和难度，并锁定选择。“下一题”清除选项与反馈；末题后回到第一题。刷新浏览器会重置会话，但已保存的数据库记录仍保留。

## 学习数据采集

当前学生固定为 `S001`。有效提交通过参数化 SQL 写入 `attempts`；提示次数和重试次数为 0，错因为空，时间戳由数据库生成。使用 `time.monotonic()` 计算题目首次呈现到首次有效提交的浮点秒数，普通 rerun 不重置计时。“下一题”开始新计时并清除记录标记。同一会话中的同一次提交只保存一次；重新进入同一道题是新的练习。

开发时可只读查看最近记录：

```powershell
python -c "from database.database import get_recent_attempts; [print(dict(row)) for row in get_recent_attempts('S001', limit=10)]"
```

## 知识掌握度

`calculate_knowledge_mastery(student_id, knowledge_point_id)` 返回一个字典；`calculate_student_mastery(student_id)` 返回按 ID 排序的 K001–K005 字典列表，含未训练知识点。

模型为 `M = 0.50A + 0.20R + 0.15S + 0.15D`，分数限制在 0–1：A 为全部正确率；R 为最近最多 5 次正确率；S 为 `R × (1 − 总体标准差)`；D 为全部记录按题目难度加权的正确率。近期按 `created_at` 倒序，同时间按 ID 倒序。计算不预先四舍五入。

无记录时，各项指标和掌握度均为 `None`，等级为“未评估”。有记录时，以 0.40、0.60、0.80、0.90 为分界，依次为“明显薄弱”“基础不足”“基本掌握”“熟练”“稳定掌握”；边界属于较高等级。

证据量为：0 次“无数据”、1–2 次“数据较少”、3–5 次“初步判断”、6 次及以上“数据较充分”，不影响分数。即使单次答对得分为 1，也须结合证据量解读。

只读查看实际结果：

```powershell
python -c "import json; from services.mastery import calculate_student_mastery; print(json.dumps(calculate_student_mastery('S001'), ensure_ascii=False, indent=2))"
```

## 学生知识画像

启动 `python -m streamlit run app.py` 后，通过侧栏在“函数训练”和“知识画像”之间切换，当前学生固定为 `S001`。画像每次访问或重新运行均调用 `calculate_student_mastery("S001")`，不缓存结果，也不修改作答数据。

总体概览显示已训练与未评估知识点数、累计答题次数及根据真实作答的正确次数与总次数汇总的正确率，不提供额外综合分数。没有作答时正确率显示“暂无数据”，全部答错时显示“0%”。Streamlit 原生 Vega-Lite 横向条形图统一使用 0–100% 横轴，只展示已评估知识点；未评估项单独列出，不绘制为 0%。每个知识点显示掌握度、掌握等级、训练次数、正确次数和证据量，可展开查看原始 A/R/S/D/M 指标。高分但数据较少时明确提示判断依据有限。无训练记录时显示“暂无训练数据”。

## 个性化学习推荐

侧栏“个性化训练推荐”展示规则式推荐目标、理由和练习预览，不直接作答。`services/recommendation.py` 提供 `recommend_next_knowledge`、`recommend_questions` 和 `generate_recommendation`，均支持临时数据库路径，不写入记录。

优先级为诊断、明显薄弱、基础不足、巩固、验证、提升。诊断与补弱保持前置知识回退；巩固按较低掌握度、较少训练次数和 ID 排序；验证按较低证据量、较少训练次数和 ID 排序；提升优先前置依赖图中深度最大的知识点，同深度再按较低掌握度、较少训练次数和 ID 排序。深度由数据库前置关系推导：无前置为 0，其余为前置最大深度加 1。前置知识未评估或掌握度低于 60% 时递归回退。高分但证据不是“数据较充分”时优先验证；全部高分且证据充分时仍返回提升推荐。

优先难度：诊断或低于 40% 为 1–2；40%–60% 为 2–3；60%–80% 为 3–4；80% 以上为 4–5，但验证使用 2–3。题目排序先区分最近 10 次是否练过，再按距目标难度的距离排序。优先新题，题库不足时补充邻近难度及旧题，并在页面标注；不会重复同一题。默认最多 5 道，实际题库可能更少。

```powershell
python -c "import json; from services.recommendation import generate_recommendation; print(json.dumps(generate_recommendation('S001'), ensure_ascii=False, indent=2))"
```

## AI 个性化学习反馈

侧栏“AI 学习反馈”先展示确定性数据，只有点击“生成 AI 学习反馈”或“重新生成”才调用当前配置的大模型服务。AI 只解释优势、待提升内容和已有推荐，不计算掌握度、正确率、等级，不决定推荐目标、题目或前置关系。文本仅作学习参考，约 250–450 中文字，包含五个固定部分。

使用 `LLM_PROVIDER` 切换 `deepseek`（默认）与 `openai`，并保留已有 `gemini` 支持。DeepSeek 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`，默认 `deepseek-flash`；Gemini 使用 `GEMINI_API_KEY`、`GEMINI_MODEL`，默认 `gemini-3.8-flash`；OpenAI 使用 `OPENAI_API_KEY`、`OPENAI_MODEL`，保留默认 `gpt-4.1-mini`。模型集中定义在 `services/llm_provider.py`，模板在 `.env.example`。统一接口 `generate_text(prompt)` 隔离官方 SDK，未来可通过同一适配器接口扩展 provider；当前不实现 groq/ollama。通过 `python-dotenv` 在启动时自动加载项目根目录 `E:\Projects\math_ai\.env`，与快捷方式的工作目录无关；系统/进程环境变量优先（`override=False`）。不要将真实密钥放入源码、文档或 Git。

没有当前 provider 的密钥时显示“DeepSeek尚未配置。”或对应服务未配置提示，训练、画像和推荐仍可正常运行，并可点击“查看规则式学习反馈”。网络、超时或 API 错误时显示安全提示并使用规则反馈。请求超时 20 秒，SDK 自动重试关闭，避免隐式重复请求。

生成结果保存在会话中，普通 rerun 不调用 API；学情、推荐数据、provider 或模型变化会清除旧结果，需再次明确点击生成。只发送必要的知识点指标和推荐摘要，不发送原始作答、SQL、数据库路径或密钥；OpenAI 请求使用 `store=False`。AI 输出不会写回数据库或确定性服务。

测试通过 mock SDK 进行，不调用真实 API。安装依赖后启动：`python -m streamlit run app.py`。在本地 `.env` 中一次性填写 `DEEPSEEK_API_KEY`，并可设置 `LLM_PROVIDER=deepseek`、`ACTIVE_TAXONOMY_VERSION=function_v2`。之后双击已有桌面启动快捷方式即可，无需每次执行 PowerShell 环境变量命令；修改 `.env` 后重启系统。`.env` 不存在时系统仍能启动，无密钥时可查看规则式反馈；函数和几何使用同一 provider 配置。`.env.example` 仅提供空的 `DEEPSEEK_API_KEY=` 模板，真实密钥不得写入文档、日志或 Git。

DeepSeek 复用 OpenAI SDK，连接 `https://api.deepseek.com`，调用 `chat.completions.create` 并读取 `choices[0].message.content`，不安装专用 SDK。只有手动运行 `python scripts/smoke_test_deepseek.py` 才进行连接冒烟测试，不自动运行。

Gemini 使用 Google 官方 `google-genai` 的 `models.generate_content` 和 `response.text`；OpenAI 保留 Responses API 与 `output_text`。Gemini 显式从 `GEMINI_API_KEY` 读取密钥，避免其他 Google 环境变量覆盖。

实现参考：[Google Gen AI SDK](https://googleapis.github.io/python-genai/)、[官方 Python SDK](https://developers.openai.com/api/reference/python)、[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)。

## 数据约定

- 中文文本统一使用 UTF-8；为兼容 Windows Excel，CSV 文件统一使用 UTF-8 with BOM。Python 读写 CSV 时使用 `encoding="utf-8-sig"` 和 `newline=""`，避免 BOM 混入首列字段名。
- `knowledge_points.prerequisite_ids`：JSON 字符串数组。初始化时校验引用；SQLite 外键不能约束 JSON 内部元素。
- `parent_id`：知识点分类层级，不等同于前置关系。五个知识点均为函数主题下的同级节点，因此为 NULL。
- `questions.options`：键为 A/B/C/D 的 JSON 对象；`answer` 为选项字母。
- `difficulty`：1–5，数值越大越难；`estimated_time`、`answer_time` 单位为秒。
- `is_correct`：0/1；`error_type`：可为空或 K/C/L/M/R/S。
- `created_at`：默认 UTC 时间字符串。

前置关系：K001 无；K002 依赖 K001；K003 依赖 K001、K002；K004 依赖 K002、K003；K005 依赖 K003、K004。

本地数据库可能包含学生信息，已加入 `.gitignore`。测试不访问真实数据库，不需要网络或凭据。后续阶段须单独明确授权。


## V0.8B 本地题库候选审核

原始资料位于 `data/raw_sources/function/`，DOCX 只读。提取器直接读取 DOCX 的 ZIP/XML，保守恢复分式、根式与上下标；无法可靠恢复的 OMML、图片和残缺题进入人工审核列表。无需新增依赖。

第一批保留29道 `reviewed` 候选，知识点/难度/标签仍需教师核对，没有任何 `approved`。候选与待核列表分别位于 `data/question_bank/candidates/` 和 `data/question_bank/review_required/`；统计与来源定位见 `reports/question_import_batch_001.md`。

```powershell
# 首次生成限定第一批；若批次已存在会拒绝覆盖
python scripts/extract_question_batch.py
# 人工逐题审核：approve / reject / skip
python scripts/review_question_batch.py data/question_bank/candidates/function_batch_001.jsonl
# 全部离线自动测试
python -m unittest discover -s tests -p "test_*.py" -v
```

`validate_candidate()` 返回 errors、warnings 和 can_approve；结构检查通过不等于数学答案已被证明。人工批准必须核对原文、公式、答案解析、知识标签和难度；修订题干/选项/答案后需使用 `content_fingerprint()` 更新指纹。

`import_questions(candidates, database_path=...)` 仅接受人工确认的 approved 题，必须显式指定隔离 SQLite 库，禁止写入真实 `math_ai.db`。其独立版本化题库支持指纹去重、事务回滚及幂等导入；`get_approved_questions()` 只返回 approved 题。当前训练、掌握度、推荐和反馈继续使用旧题库；15节点正式接入需另行验收迁移，不会将新 K005 奇偶性混同旧 K005 参数题。


## V0.8C 金标准题人工审核

第一批29道原候选是只读快照。V0.8D 已依据用户明确完成的人工审核生成29道 approved，审核身份为 manual_user；原候选仍为 reviewed 快照。

```powershell
python scripts/review_question_batch.py --reviewer "教师姓名"
# 普通重启自动从尚未审核题继续；显式重看 skip 的题
python scripts/review_question_batch.py --reviewer "教师姓名" --revisit-skipped
# 只重建导出和统计，不进行审核
python scripts/review_question_batch.py --prepare
# 审核后导入自动创建、自动清理的临时 SQLite 并验收
python scripts/verify_question_review.py
```

逐题显示原文、答案解析、来源定位、知识点、标签、难度与指纹。输入 a/r/s/q 分别批准、拒绝、跳过、保存退出。批准需要输入 confirm 明确核对数学 checklist；每项决定记录审核人、UTC 时间和备注。非 complete、校验错误或 warning 不能批准，本版不允许覆盖 warning。数学问题需要独立修订流程，本次不更改原候选内容。

审核日志：`data/question_bank/reviews/function_batch_001_review.jsonl`。
批准导出：`data/question_bank/approved/function_batch_001_approved.jsonl`。
统计报告：`reports/question_review_batch_001.md`。

审核日志绑定原候选 SHA-256，变更快照或篡改题目内容时拒绝恢复。每次决定先原子保存日志，再更新导出；导出中断可用 --prepare 重建。并发审核会被锁阻止；异常终止留下 .lock 时，应确认没有审核进程后再移除该锁。

临时库验收保留旧题和已有虚拟 attempts；另建完全可丢弃的15节点验收投影，只放 approved 题，复用训练、掌握度、推荐、画像和规则反馈逻辑验证。15节点枚举适配仅在验收作用域内生效，真实应用仍使用原架构。未评估保持 None，related 标签不会重复计入证据；无题知识点显示暂无金标准题。K007 暂无金标准题，需要 Batch 002 定向补充，本阶段不处理第二批。


## V0.8D Batch 001 批准与临时集成验收

批准前29道全部通过 validator，ID和指纹唯一。批准导出及审核日志保留用户确认与审核时间，不代表 AI 再次审核。真实数据库尚未迁移。

`python scripts/verify_question_review.py` 仅在临时库导入，首次 inserted=29，重复 inserted=0/skipped=29。沙盒适配只在离线验收作用域内生效：训练SQL显式限制 approved，掌握度仅统计 primary，旧 Q005/Q006 不进入新 K005；推荐检查 core 与 question prerequisite（None 或 <0.60 均不满足），优先未近期作答题，无题返回覆盖不足状态。真实应用仍使用原数据库和服务入口。

覆盖分析见 `reports/question_bank_gap_after_batch_001.md`。门槛为每节点至少3道、至少1道难度1–2、至少1道难度2–3；难度2可同时满足两项。覆盖不足不改变学生掌握度。K007 当前0题，需要后续 Batch 002 定向补充；本阶段只分析缺口，没有处理第二批。


## V0.9A function_v2 完整隔离演练

三个已人工批准批次合计66道题，每个知识点至少3道。真实数据库仍使用 function_v1，未迁移或切换。演练结果见 `reports/function_v2_final_coverage_report.md` 和 `reports/function_v2_dry_run_validation.json`。

`python scripts/function_v2_dry_run.py` 用 SQLite backup API 创建 `tmp/function_v2_dry_run.db`，只在副本执行新增版本表与66题导入，复用真实 mastery/recommendation 查询接口，验证历史映射、新学生、模拟训练和回退。为防止覆盖副本，该命令拒绝已存在的目标文件；迁移函数本身支持幂等重复执行。

PowerShell 中可以启动隔离版本（只改变当前终端配置）：

```powershell
$env:MATH_AI_DATABASE_PATH = (Resolve-Path tmp/function_v2_dry_run.db).Path
$env:ACTIVE_TAXONOMY_VERSION = "function_v2"
python -m streamlit run app.py
```

切回旧版本用 `$env:ACTIVE_TAXONOMY_VERSION = "function_v1"`。恢复真实库路径用 `Remove-Item Env:MATH_AI_DATABASE_PATH`；生产默认仍为 function_v1。AI 请求只在明确点击按钮时发生，测试全部 mock，演练不发送真实 API 请求。

版本化映射以关系表为事实来源。新增题在旧 questions 外键上使用 `function_v2:Kxxx` 兼容节点，其 topic 为 function_v2，不进入旧版本题池；不修改旧题正文、答案、旧外键及任何历史 attempts。新表提供15节点图、primary/related映射、题级前置、标签、来源和迁移审计。related 不计直接证据，新 K005 奇偶性不继承旧参数题分数。

本阶段迁移函数明确禁止真实库路径。正式启用仍需用户另行授权对真实库进行受控迁移、复核原记录及备份，再设置 `ACTIVE_TAXONOMY_VERSION=function_v2`；不能仅设置版本变量而跳过数据库迁移。回退只需切回 function_v1，不删除新作答。

## V1.0A 首次函数诊断测评

入口仍为 `app.py`。首页和导航新增首次诊断；侧栏可输入本地学生编号（默认 S001），各页面共用该编号，不涉及账号注册。建议新学生用一个未使用过的编号，例如 S_NEW_001。

诊断默认18题，每题提交后仅提示“回答已记录”，自动进入下一题，不显示答案或解析。选题来自 function_v2 的 approved primary 题池，难度优先1–2、必要时3；先对 K001/K002 各作两次基础探测，再按未测节点、前置图深度及难度进行确定性选择。前置至少两次作答且正确率低于50%时降低其后继优先级，保留广度探测；诊断探测不等同于允许进入高级训练，后续 recommendation 仍执行严格前置检查。无合适题目记录覆盖限制，题量不足时提前结束。

`services/diagnostic.py` 负责选题、评分、测评生命周期和结果解释；`database/diagnostic.py` 负责向后兼容的旁路表。首次点击开始才创建 diagnostic_sessions 和 diagnostic_answers，不修改原 attempts schema 或旧记录，也不重跑 V0.9 迁移。诊断答案仍写入原 attempts；关联表标记 attempt_mode=diagnostic。写入作答、唯一关联和下一题状态使用同一事务，重复请求不会新增作答。数据库恢复当前题和计时，浏览器刷新、普通 rerun 或重新打开页面可续答；完成结果保存快照，仅明确点击“重新诊断”开始新测评，保留此前真实作答证据。

结束展示正确率、15节点画像、四类确定性解释、覆盖限制及已有 recommendation 服务生成的学习目标和练习。“开始针对性训练”进入训练页面并限定推荐题池。分组沿用已有 taxonomy：K001–K002 基础概念、K003–K006 函数性质、K007–K011 基本初等函数、K012–K015 函数综合应用。无证据显示未评估，少量证据显式提示不确定性；重复诊断不删除历史证据，结果画像包含完成时的历史与本轮作答。

V1.0A 最初使用专用试用库 tmp/function_v1_0a_local.db。V0.9B 正式迁移后，本地默认直接读取真实 math_ai.db 和 function_v2。若要继续使用隔离试用库，可运行：

```powershell
$env:MATH_AI_DATABASE_PATH = (Resolve-Path tmp/function_v1_0a_local.db).Path
$env:ACTIVE_TAXONOMY_VERSION = "function_v2"
python -m streamlit run app.py
```

访问 http://localhost:8501。保持两个配置用于本地试用；切换 function_v1 仍可回退使用原训练、画像和推荐。

离线验证：`python -m unittest discover -s tests -p "test_*.py"`。新增测试验证选题、无证据、事务幂等、刷新恢复、完整画像、前置降权、缺题、重测、旧版回退及真实页面导航，不调用 LLM。

## V0.9B 真实数据库正式迁移

真实 `math_ai.db` 已经通过用户明确授权的正式迁移，function_v2 注册为 active；function_v1 保留为可回退视图。复用 V0.9A 的同一 schema、图、66道人工批准题和旧题映射，未删除旧表或旧行，未改动或重新评分历史 attempts。Q005 主映射 K003、Q006 主映射 K004，两题 related 均为 K007，新 K005 奇偶性不继承旧参数题。

唯一生产 CLI：`python scripts/migrate_function_v2.py --production`。生产 opt-in 才允许真实路径，默认演练入口继续拒绝真实库。CLI 在写入前记录绝对路径、PRAGMA table_list、题数和 attempts 数量及全字段摘要。迁移使用 BEGIN IMMEDIATE，在提交前验证旧知识点/题目原行和全部 attempts 完全保持、15节点及无环图、approved primary 唯一、旧映射和外键；任何检查失败整笔回滚。重复相同清单 inserted=0/skipped=66，清单摘要改变时拒绝覆盖。

已完成迁移，不需再次运行迁移或初始化。现在启动正式网页：

```powershell
# 若当前终端曾使用隔离库或旧版本配置，先清理覆盖配置
Remove-Item Env:MATH_AI_DATABASE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:ACTIVE_TAXONOMY_VERSION -ErrorAction SilentlyContinue
python -m streamlit run app.py
```

默认版本只由 settings.py 统一定义为 function_v2，所有查询和页面读取同一配置；环境变量仍可显式覆盖用于隔离测试或 function_v1 回退。诊断可在正式 V2 库使用；点击开始及提交才保存测评，迁移和页面验收不会模拟写入真实 attempts。训练和推荐页面隐藏题目内部 ID。

完整自动测试仍运行 `python -m unittest discover -s tests -p "test_*.py" -v`。旧版测试显式选择 function_v1，V2 测试显式选择 function_v2，所有写入测试使用临时数据库。生产验收报告为 reports/function_v2_production_validation.json（已忽略），测试日志为 tmp/v0_9b_tests.log。

## V1.0B 自适应训练系统

入口和导航继续使用 app.py。V2 的“开始训练”页面现在提供“开始个性化训练”和“选择知识点训练”。首次诊断结束的“开始针对性训练”创建真实 adaptive session，不再固定传递一套推荐题。当前活动 session 可跨刷新和页面切换恢复；普通 rerun 不新建 session、不提交答案、不跳题。只有明确点击“下一题”重新选择下一道题；已提交题先显示正确/错误和解析。

services/recommendation.py 决定学什么，并为手动选择和活动目标复用同一递归前置回退。services/adaptive_training.py 决定该目标下下一题及训练状态；始终只读 approved V2 主映射题，必要核心前置及题级前置必须满足，related 不作为门槛。一个 session 不自动跳到其他目标：目标完成、必要前置不足、题库不足或主动结束时先结束本轮，显示下一步建议，再由学生开始新一轮。

初始建议难度：未评估或掌握度低于40%为1（优先1–2），40%–80%为2（允许相邻题），80%–90%为3，至少90%为4。少量证据会限制起始难度；两题以内最高建议2。连续两题正确且最近准确率至少60%时，结合最新掌握度、证据量和实际题目难度最多提高一档；连续至少两题错误逐步降低一档。建议难度限1–5，低掌握度最高2，不因偶然两题正确跳到5。实际选题仅在建议难度及相邻档位内寻找，安全上限还受证据量限制。

每题 attempt 保存后，在同一事务内调用原 A/R/S/D mastery 服务，读取包含本次未提交事务内作答的掌握度，再更新 session 状态。mastery 公式没有改变。下一题优先当前难度的新题，再相邻难度的新题；默认避开最近10次 attempts，必要时使用此前做过但本轮未做过的相邻题。每个 session 内题目唯一；无安全、满足前置的题时显示覆盖不足，不复用本轮题目或生成新题。

停止条件：至少5题且最近3题至少2题正确、掌握度达到80%；或者8题；或者必要前置不足、连续3题失败且掌握度低于40%、题库不足、主动结束。根节点失败时建议巩固当前基础，不凭 related 标签伪造前置回退。结束显示知识点、正确率、训练前后掌握度、实际题目难度轨迹、建议难度变化、停止原因和现有 recommendation 服务生成的下一步建议。部分节点题量少，可能不足5题就因覆盖限制结束；没有扩充题库。

database/training_sessions.py 提供向后兼容 migration：training_sessions 保存身份、体系、目标、起止时间、状态、初始/最终掌握度及轻量 state_json；training_session_questions 保存题目顺序、实际难度、唯一 attempt_id 和 attempt_mode=training。schema_migrations 登记 v1_0b_training_sessions。原 attempts schema 和历史行不变：诊断通过原 diagnostic_answers 标识 diagnostic，新训练通过关联表标识 training，无关联的历史记录标识 legacy。选题、作答、关联记录和状态保存均使用事务；重复提交（含并发）只写一次，失败回滚。V1 页面由 pages/_training_v1.py 保留原训练行为，不另建入口。

运行库已完成本阶段 session schema migration，无需重跑。新环境可运行 `python scripts/migrate_adaptive_training.py`，或首次开始训练时自动执行同一个幂等 migration。迁移前后校验全部旧知识点、题目和 attempts 原行保持一致，不重跑 taxonomy migration。

DeepSeek 不参与选题、评分、掌握度、升降难度、前置及停止判断。本阶段使用规则训练总结；结束后可进入已有 AI 学习反馈页解释已有结果，无 Key 可查看规则反馈。

运行仍为 `python -m streamlit run app.py`，默认真实数据库和 function_v2。完整离线测试273项通过，包含28项新增 adaptive 测试；日志 tmp/v1_0b_tests.log。网页验收使用迁移后真实库的一次性副本，经 Streamlit AppTest 完成18题诊断、查看画像、5题自适应训练、更新推荐和规则反馈；真实服务各路径 HTTP 200。验收报告 reports/v1_0b_validation.json：示例实际难度2→2→2→3→4、函数单调性掌握度0%→88.9%、推荐K003→K004，真实库未新增测试作答。

## 推荐页与自适应训练衔接修复

个性化推荐页面负责“学什么”，不负责答题。推荐数据是有意省略选项和答案的预览；真实训练查询在数据库层将 questions.options JSON 反序列化为 A/B/C/D 字典。已核对66道新增 approved 题的选项全部完整且与原 JSONL 一致，未重导题库或修改题目。

推荐页显示目标名称（默认隐藏内部知识点编号）、推荐类型、掌握度、证据量、建议难度、推荐原因和预计5题/最多8题。主要按钮“开始推荐训练”调用 start_training_session，明确传入当前推荐知识点及 lock_target=True，然后进入训练页面。相同目标的活动 session 续答；不同目标的旧 session 先按主动切换结束并保留全部记录，再在同一事务内创建指定目标的 session。必要前置已变化时提示刷新推荐，不静默改换知识点。诊断入口复用同一目标锁定规则；自由进入训练页面仍允许 recommendation 自动选目标。

推荐预览最多显示4条难度信息，并最多提供一道折叠题干预览，明确标注“进入训练后可正式作答”。题干、A/B/C/D、提交、反馈、下一题和持久化仍只由训练页面与 adaptive service 处理。训练结束可查看本次结果、查看学习画像和继续个性化推荐。function_v1 继续进入保留的旧版训练。

services/math_text.py 提供统一、仅用于显示的数学渲染，推荐、训练和诊断共享使用：如 9^(a)、3^(2a+b)、log_(3)4、a_(n)、sqrt(x+1)、root(3,x+1) 转为行内 LaTeX。保留普通中文和现有 LaTeX；未知、残缺或歧义表达保持原文，不计算表达式、不改题目数学含义、不改原始数据。训练/诊断选项仍以字母提交，排版不影响评分。

完整自动测试286项通过（新增13项），日志 tmp/recommendation_integration_tests.log。验收 reports/recommendation_training_integration_validation.json：真实库副本中，推荐→创建指定目标 session→连续作答3题成功，选项完整、目标一致、仅新增3次真实提交对应的测试 attempts；生产数据保持不变。真实服务各页面 HTTP 200，仍使用 app.py。
# V1.0C：错因诊断、渐进提示与变式基础

本阶段只使用本地 SQLite 和确定性 Python，不联网抓题，不扩展教师端或 V1.0D。

- 运行 `python scripts/migrate_variation.py` 可添加新结构；训练页也会幂等初始化。
- 运行 `streamlit run app.py`，使用 `function_v2` 训练页。旧 `function_v1` 页保留原行为。
- 四个按钮分别提供方向、方法/知识点、关键步骤、完整解析；不再在提交后自动显示完整解析。每次点击产生一条 `training_hint_events`，计数保存于 session；提交 attempt 时保存当时的累计提示计数。提交后使用的提示记录在 session 事件中，不追改原作答快照。静态题使用知识点规则提示，模板题使用与参数配套的提示。
- 错误后学生在“你觉得自己主要卡在哪里？”中自选 K/C/L/M/R/S，再点击“保存错因”。建议由作答时间、已用提示级别的规则产生，仅为建议；未选择时保留 NULL。学生选择写入当前错误 attempt，不改答案与正确性。
- “再试一次”增加 session 和当前题的 retry_count；再次提交新增 attempt。第一次错误保留；重试不占新的训练题数，也不触发连续两道新题的升降难度。所有 attempts 仍交给原 mastery 服务计算，结束正确率按首次作答统计。
- recent_question_ids 取最近30道不同已做题，重试不缩小窗口。同轮所有已曝光题不能再作为下一题。先选新题，再放宽难度（保留安全上限与前置门槛），之后才按较早历史优先回退。模板参数组合在近期曝光窗口内禁止回退重用。
- 5个技术验证模板：二次函数对称轴、二次函数顶点、指数函数基本性质、根式定义域、幂函数奇偶性。分别映射新体系 K007/K007/K009/K002/K005；静态新题不足时才生成一个变式。参数为有限整数域；二次函数使用非零 a 与整数顶点参数，展开成 a,b,c。
- generator 构造题干和选项；validator 使用展开系数的有理数计算或定义独立验证唯一正确选项。固定 seed 或 parameter_set 可复现。参数合法性、四个不同选项、标准答案、指纹均校验；训练提交前重新校验生成题。
- variant_fingerprint 为 template_id + 排序后的参数 JSON 的 SHA-256，数据库 UNIQUE 保证参数组合只有一个题目身份。生成题保留 template_id、parameter_set、generator_version、提示和 generated_template 来源；沿用 approved 映射与现有推荐、前置知识机制。
- source_url、license、usage_note 只预留于轻量来源元数据结构。以后网络资源必须明确来源与许可，进入 reviewed，人工审核并 approved 后才训练；本阶段没有抓取接口。

验证：`python -m unittest discover -s tests -q`。新测试位于 `tests/test_variation_training.py`，使用临时数据库和 Streamlit AppTest，不需要 API 或网络。

手工验收：开始训练 → 连点提示1/2/3/完整解析 → 故意答错 → 选择并保存错因 → 再试一次 → 提交正确答案 → 下一题 → 结束本轮，检查提示次数、重试次数和主要错误类型。刷新应恢复当前题与已保存计数；数据库应保留首次错误及重试两条记录。
# V1.0D：多题型训练基础

现有训练引擎支持 single_choice、fill_blank、subjective。填空题使用离线 SymPy 与确定性规则判分，主观题只保存文本/图片引用，未评分题不会影响掌握度。详细 schema、比例规则、导入边界与未来 OCR 流程见 [多题型说明](docs/multi_type_engine.md)。

运行 `python scripts/migrate_multi_type.py` 幂等迁移，运行 `streamlit run app.py` 使用训练页。首批本地 DOCX 候选为25道填空、16道主观题，全部 reviewed，尚未导入正式训练。人工审核文件位于 `reports/function_fill_blank_batch_001_可读版.docx` 和 `reports/function_subjective_batch_001_可读版.docx`。

## V1.0D.1：多题型待审题库扩充

重新扫描全部15份本地DOCX，输出20道多选、35道填空、14道解答题，全部 reviewed。多选使用 correct_answers 集合判分；填空支持 canonical_answer 与有限实数 set；大题使用 sub_questions 和对应 rubric，未评分不影响掌握度。未调用 LLM、网络或 OCR。

旧文件保留：新多选为 batch_001，新填空/解答为 batch_002。可直接打开 reports/function_multiple_choice_batch_001_可读版.docx、reports/function_fill_blank_batch_002_可读版.docx、reports/function_subjective_batch_002_可读版.docx 审核。22道填空与14道解答复用了此前尚未批准的来源题；不能把重新结构化计作正式新增 approved。

候选与同名 review_required 文件一致。覆盖与缺口报告位于 reports/function_multitype_question_bank_report.md，临时库验收位于 reports/v1_0d_1_validation.json。只在隔离数据库升级四题型 schema、模拟导入和训练；真实数据库、approved 文件及历史 attempts 均保持不变。完整约束和命令见 [多题型说明](docs/multi_type_engine.md)。本阶段完成后等待人工 Word 审核，不自动批准或正式导入。

## V1.0D.2：多题型正式训练

用户审核的三份 batch_001 已批准并正式导入：多选20、填空25、主观16。当前正式题库133道，单选72道保留；batch_002 继续待审。运行 `python -m streamlit run app.py`，从首页进入“开始训练”。多选用多选控件、集合全对判分；填空用确定性数学 evaluator；大题显示小问和总分，保存文本或图片后待评阅。无法安全判分的填空保存为 needs_manual_review；待评填空和大题均不影响掌握度。

训练按掌握度混合题型并回避近期原题，结束显示题型分布、已评分正确率和待评数量；画像区分有效证据和待评阅作答。图片只保存在忽略提交的 attachments/，不运行 OCR、不由 LLM 决定客观题正确性。

SQLite一致性备份、导入数量与历史作答摘要见 reports/v1_0d_2_production_validation.json；原33条 attempts、原题和 function_v1 已验证保持完整。审核审计见 data/question_bank/reviews/function_multitype_batch_001_manual_user_audit.jsonl。全部离线测试命令仍为 `python -m unittest discover -s tests -q`。无需重跑 init_db 或迁移脚本。
### V1.0D.3 多题型诊断与训练

首次诊断默认18题，优先覆盖K001–K015，目标题型为单选6、多选2、填空7、解答3。页面使用对应作答控件，确定性判分与待评阅结果分开统计。旧未完成诊断会保留已答记录并升级剩余题池。

自适应训练按掌握度、会话题型缺口、前置知识、难度与最近30题曝光选择下一题，降低选择题比例。未评分大题和需人工审核的填空只保存，不影响掌握度或即时难度。详见 [V1.0D.3报告](reports/function_multitype_diagnostic_adaptive_report.md)。

### V1.0D.4 数学公式规范与清洗

题目统一使用普通文本与单美元包围的标准LaTeX片段，学生页面共用 `render_math_text`。导入、选题和缓存恢复检查公式状态；只有 approved 且公式 valid 的题可训练。安全转换已应用于128题，5题因根式结构或表达式作用范围不确定而暂停训练，133题及历史学习记录保留。

完整字段审计、修复计划和截图题来源追踪见 [公式清洗报告](reports/function_v2_math_formula_audit.md)。网页验收在隔离副本中完成18题诊断和10题训练；真实库修改前使用SQLite backup API备份，attempts与掌握画像摘要均不变。运行 `python -m unittest discover -s tests` 验证离线回归；审计脚本默认只生成计划，正式应用需要显式生产授权参数。

### V1.1C 立体几何与空间向量正式训练

本阶段已完成正式导入123道立体几何题，正式题库共256道；原函数题池及79条历史作答保持完整。首页或侧栏可切换“函数”和“立体几何与空间向量”，诊断、训练、画像、推荐及反馈按专题隔离。

题干图和选项图在作答前显示，解析图在提交后查看解析时显示。必需题图缺失或损坏的题会跳过；待修复的99道候选不进入正式训练。主观题继续保存作答并等待人工评阅。

启动命令：`python -m streamlit run app.py`。无需重新初始化或导入题库。完整验收记录见 [V1.1C正式导入报告](reports/geometry_v1_1c_production_report.md)，批准题目与图形可查看 [Word预览](reports/geometry_production_approved_preview.docx)。离线回归命令：`python -X utf8 -m unittest discover -s tests -q`。

### V1.1D 覆盖审计与几何训练质量

正式geometry_v1题池仍为123题。二次恢复仅处理原99条needs_manual_fix候选；98条成功恢复并分段为113道独立练习，1条特殊字体字形不明确而继续阻断。恢复题全部reviewed、待人工确认；不自动批准或正式导入。

几何训练使用D1/D2、D2/D3、D3/D4、D4/D5的掌握度梯度并报告缺题；诊断默认15题，少量独立证据显示“证据不足 / 待进一步训练”。选题用来源位置和内容指纹回避同一原题及近期曝光。函数流程保留原规则。

查看[覆盖审计](reports/geometry_v1_1d_coverage_audit.md)、[恢复审核Word](reports/geometry_recovery_batch_001_可读版.docx)及[最终报告](reports/geometry_v1_1d_final_report.md)。离线恢复命令为`python -X utf8 scripts/recover_geometry_batch.py`，该脚本只读正式库并输出审核资料，没有production import选项。


## Streamlit Community Cloud Deployment

唯一入口是 `app.py`。本地继续运行：

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

使用 Python 3.11（本地验证环境）部署。运行依赖列在 requirements.txt，不含测试工具。

1. 将代码、requirements.txt、`data/deployment/question_bank.db` 和 `data/question_assets/images/` push 到 GitHub。先审查待上传文件，勿上传学生记录或原始素材。
2. 登录 https://share.streamlit.io 。
3. 点击 Create app。
4. 选择 GitHub repository。
5. branch 选择 `main`。
6. entrypoint 填写 `app.py`。
7. 打开 Advanced settings / Secrets。
8. 添加以下 TOML 示例，并将占位符替换为自己的 DeepSeek Key：

```toml
LLM_PROVIDER = "deepseek"
DEEPSEEK_API_KEY = "your-key"
ACTIVE_TAXONOMY_VERSION = "function_v2"
```

9. 点击 Deploy。
10. 获取固定的 `https://<app-name>.streamlit.app` URL，手机、平板及其他电脑均可通过浏览器访问。侧栏“部署健康检查”显示数据库、两专题题库、题图及 DeepSeek 配置布尔状态，不显示 Key。

官方步骤：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
Secrets 说明：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

配置统一通过 `settings.get_setting` 读取，优先级为进程环境变量 > Streamlit st.secrets > 项目根目录 .env > 默认值。本地 .env 继续有效；`.streamlit/secrets.toml` 被 Git 忽略，config.toml 不含密钥。空环境变量可显式禁用对应配置。

`data/deployment/question_bank.db` 是不含学生记录的基础题库；`scripts/prepare_cloud_database.py` 从本地数据库导出并清空所有非题库表，不改动本地数据库。已有导出文件时脚本拒绝覆盖，更新前需要审查。首次启动缺少 math_ai.db 时复制基础题库为运行数据库；已有本地数据库保持原样。

**SQLite 云端限制：** Community Cloud 本地文件不应当作可靠的长期多人持久化存储。答题、诊断和训练记录仍写入运行 SQLite，但重启、重新部署或实例替换后可能丢失，不保证持久化。临时 Streamlit session 也会结束。当前学生编号不是身份认证，不适合承载正式多人私密学习数据。

数据库访问保留在 database 层。预留 `DATABASE_URL`，当前仅接受 `sqlite:///相对路径` 或 SQLite 绝对路径；非 SQLite URL 明确报错，未来可在数据库层接入 PostgreSQL。本阶段没有迁移。

不上传目录包括 backups/、tmp/、data/raw_sources/、data/student_submissions/、__pycache__/；.env、*.pyc、本地数据库及 secrets.toml 同样被忽略。部署题库是明确例外。正式题图使用项目根目录相对路径，必须随代码上传。
