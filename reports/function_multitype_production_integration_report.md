# V1.0D.2 多题型正式接入验收

用户明确人工审核的 batch_001：多选20、填空25、主观16，共61道。全部复检 validator 通过，无阻止批准题。
原 candidates 保持 reviewed、未覆盖。approved 文件保留原题内容与指纹，reviewed_by=manual_user，备注“用户已基于可读版完成人工审核。”。审核审计绑定候选和 Word SHA-256。
batch_002 没有批准或导入。

| 正式题型 | 数量 |
|---|---:|
| single_choice | 72 |
| multiple_choice | 20 |
| fill_blank | 25 |
| subjective | 16 |

SQLite backup API 一致性备份：`E:\Projects\math_ai\backups\math_ai_before_v1_0d_2_20261006T152122466066Z.sqlite3`。
导入首次新增61，重复新增0、跳过61。导入事务、外键校验、失败回滚已在临时库测试。
原72道题（含原66道金标准新增题）保持不变，function_v1 仍返回原6道种子单选。
历史 attempts：33条；导入前后 SHA-256 `64ddc6ba497cc9fa490172c5abe6c74428128556ac366dce9947c6640554164f` 完全一致。

## 判分与未评分作答

多选集合完全相同得1，否则0；选项顺序不影响，不计部分分。填空通过受限 AST/SymPy 与规则 evaluator，支持 numeric、expression、interval、set、text 和轻量输入归一化。不由 LLM 决定正确性。
无法安全解析的填空保存为 needs_manual_review，is_correct=NULL，暂不计 mastery。大题保存文本与随机文件名图片引用，status=submitted_pending_review、score=NULL，不自动判错或计算总分。
主观图片沿用 attachments/，校验真实PNG/JPEG/WEBP、10MB上限与像素尺寸。SQLite无图片BLOB。subjective_submissions 关联唯一 attempt_id；answer_review_requests 记录填空人工审核原因。
小问包装只添加原评分点与原解答的对应引用，不改已审核题干、答案、评分点文字或分数；rubric_source=derived_for_system，不声称官方评分细则。
pending details 一律排除有效掌握证据，即使误写非空 is_correct。画像、训练总结与只读反馈区分已评分证据、待评阅大题和待审核填空。推荐逻辑不因 pending 作答变差。

## 自适应题型

| 掌握度 | 选择类（单选/多选共享） | 填空 | 大题 |
|---|---:|---:|---:|
| 未评估或 <40% | 80% | 20% | 0% |
| 40–70% | 60% | 40% | 0% |
| 70–85% | 40% | 60% | 0% |
| ≥85% | 25% | 50% | 25% |

题型按比例缺口确定性选择，缺题时回退；始终遵守前置与安全难度。先未做/未见题，再近期30题回避，按题号、来源指纹、变式指纹和原段落防止同一原题跨题型重复曝光。

## 真实网页与自动测试

371项全部通过，新增22项；原有349项保留通过。最终日志 tmp/v1_0d_2_final_tests.log。
本地 Edge 无界面浏览器连接真实 Streamlit HTTP 服务，使用正式库副本和合成作答/图片；没有向生产库写入验收作答。
| 网页题型 | 实际交互结果 |
|---|---|
| 单选 | radio显示、选择、提交，判对 |
| 多选 | multiselect显示，按逆序多选，集合判分正确 |
| 填空 | 无radio，输入1.50000000000000，与标准分数答案等价，判对 |
| 大题 | 两小问与总分显示；文本输入和合成PNG实际上传；图片文件引用与submitted_pending_review保存；mastery不变 |

网页报告 reports/v1_0d_2_browser_validation.json 包含各题ID和截图路径；截图只存 tmp/。Streamlit AppTest 另覆盖 pending 填空提示、大题显示、画像和既有训练流程。

## 文件、命令与安全

新增/修改文件与执行命令完整清单见 reports/v1_0d_2_final_validation.json。backups/、tmp/、attachments/、student_submissions/、data/student_submissions/、.env 均经 git check-ignore 核实；未commit，未提交学生图片。
不运行OCR，不让DeepSeek评分，不进入下一版本。下一步运行 python -m streamlit run app.py，从首页进入“开始训练”，按学情进行多题型练习。
