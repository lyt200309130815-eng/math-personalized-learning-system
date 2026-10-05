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

使用 `LLM_PROVIDER` 切换 `deepseek`（默认）与 `openai`，并保留已有 `gemini` 支持。DeepSeek 使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`，默认 `deepseek-flash`；Gemini 使用 `GEMINI_API_KEY`、`GEMINI_MODEL`，默认 `gemini-3.8-flash`；OpenAI 使用 `OPENAI_API_KEY`、`OPENAI_MODEL`，保留默认 `gpt-4.1-mini`。模型集中定义在 `services/llm_provider.py`，模板在 `.env.example`。统一接口 `generate_text(prompt)` 隔离官方 SDK，未来可通过同一适配器接口扩展 provider；当前不实现 groq/ollama。当前直接读取进程环境变量，不自动加载 `.env`，无需 python-dotenv。不要将真实密钥放入源码、文档或 Git。

没有当前 provider 的密钥时显示对应的“尚未配置 DeepSeek AI 服务。”等提示，训练、画像和推荐仍可正常运行，并可点击“查看规则式学习反馈”。网络、超时或 API 错误时显示安全提示并使用规则反馈。请求超时 20 秒，SDK 自动重试关闭，避免隐式重复请求。

生成结果保存在会话中，普通 rerun 不调用 API；学情、推荐数据、provider 或模型变化会清除旧结果，需再次明确点击生成。只发送必要的知识点指标和推荐摘要，不发送原始作答、SQL、数据库路径或密钥；OpenAI 请求使用 `store=False`。AI 输出不会写回数据库或确定性服务。

测试通过 mock SDK 进行，不调用真实 API。安装依赖后启动：`python -m streamlit run app.py`。真实 API 验证请自行配置环境变量后手动点击按钮。

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
