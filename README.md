# 高中数学个性化 AI 训练系统

教师主导、AI 辅助的数学训练项目。当前完成 **V0.1 数据库基础**及 **V0.2 学生训练页面**，覆盖函数模块 K001–K005。尚无答题记录采集、掌握度算法、推荐系统或 LLM 接入。

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
- `pages/training.py`：中文题目、单选、提交反馈和下一题；状态只保留在当前会话。
- `database/database.py`：统一连接，启用外键，返回 `sqlite3.Row`；调用者负责关闭连接。
- `init_db.py`：事务内创建三张表，初始化知识点并导入题库。
- `data/questions.csv`：六道函数单选题及答案、解析。
- `tests/test_database.py`：使用临时数据库的离线自动测试。
- `tests/test_training.py`：题库读取、JSON 校验及 Streamlit 交互测试。

## 函数训练

页面从 SQLite 查询题目及知识点名称，按题目 ID 排序，不直接读取 CSV。初始无选中答案，提交后显示对错、正确答案、知识点和难度，并锁定选择。“下一题”清除选项与反馈；末题后回到第一题。刷新浏览器会重置会话。本阶段不写入 `attempts`。

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
