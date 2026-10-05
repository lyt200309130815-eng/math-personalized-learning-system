# 高中数学个性化 AI 训练系统

教师主导、AI 辅助的数学训练项目。当前完成 V0.1–V0.6，覆盖函数模块 K001–K005。推荐使用确定性规则，未使用机器学习或 LLM，尚未实现自动学习计划或 AI 学习反馈。

已实现：SQLite 数据基础、高中函数题库、Streamlit 学生训练、学习行为采集、知识掌握度分析、学生知识画像和个性化学习推荐。

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
- `database/database.py`：统一连接，启用外键，返回 `sqlite3.Row`；调用者负责关闭连接。
- `init_db.py`：事务内创建三张表，初始化知识点并导入题库。
- `data/questions.csv`：六道函数单选题及答案、解析。
- `tests/test_database.py`：使用临时数据库的离线自动测试。
- `tests/test_training.py`：题库读取、JSON 校验及 Streamlit 交互测试。
- `tests/test_attempts.py`：作答持久化、最近记录查询和计时、防重复提交测试。
- `tests/test_mastery.py`：临时数据库中的指标、等级边界、证据量及只读计算测试。
- `tests/test_profile.py`：画像格式、未评估处理、最新数据读取及页面导航测试。
- `tests/test_recommendation.py`：临时数据库中的推荐规则、题目选择及页面测试。

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
