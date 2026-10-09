# V1.1B Geometry 人工审核包与图形验证

clean_candidates：102；warning_candidates：159。
V1.1A 原有警告题 73 条全部保留，新增检查涵盖答案/解析缺失、非题目边界、低质量图和低置信图题关联。
clean 仅表示程序未检出问题，绝非已完成人工核验。题型、一个primary及related、难度和asset_role均为待人工确认建议。

| 批次 | 来源 | 候选数 | 嵌入图像数 |
|---|---|---:|---:|
| Batch01 | §7.1 / §7.2 | 53 | 71 |
| Batch02 | §7.3 / §7.4 | 59 | 90 |
| Batch03 | §7.5 / §7.6 | 62 | 62 |
| Batch04 | §7.7 / §7.8 | 41 | 64 |
| Batch05 | §7.9 / §7.10 | 28 | 56 |
| Batch06 | 必刷小题13 / 必刷大题14 | 18 | 26 |

## 图形验证

- question_diagram：166（角色草标，尚未人工确认）
- solution_diagram：180（角色草标，尚未人工确认）
- option_image：0（角色草标，尚未人工确认）
- decorative：0（角色草标，尚未人工确认）
- unknown：61（角色草标，尚未人工确认）
- 38个未关联图形：38 个保持 question_id=null、human_action=pending；无自动绑定。
- MISSING REQUIRED DIAGRAM：1 条；无批准建议。
- 图片原始哈希/解码错误：0。
- 已检查369个关联实例的题目段落范围、来源哈希、列表成员关系、表格上下文及跨题媒体复用；逐项证据见 asset_verification.jsonl。
- 第二张图遗漏检查以源图形占位数量与关联实例数比较；人工仍须核查上下文语义。
- question_diagram/option_image 为未来学生题干可用角色；solution_diagram仅用于解析。所有student_render_enabled=false。
- 表格图或角色不明的图形保持unknown；不凭像素/上下文自动认定装饰，decorative需人工确认。
- 图片按原始比例、150dpi自然宽度显示，最大宽度6英寸、最大高度8英寸。短边<100px或长边<240px显示IMAGE QUALITY WARNING；不放大低分辨率图。
- TIFF等转为PNG只用于Word嵌入，原始媒体不变；不生成Word页面截图。

## 重复题（仅报告）

- exact_duplicate：0 组/匹配记录。
- normalized_text_duplicate：0 组/匹配记录。
- same_source_duplicate：0 组/匹配记录。
- repeated_source_number：33 组/匹配记录。
- existing_bank_fingerprint_matches：0 组/匹配记录。
- 现有题库检查 436 条记录，其中真实数据库只读检查 133 条；删除0条。
- same_source_duplicate按同来源哈希+同XML位置；重复题号另列，章节题号重置不视为重复题。
- exact按题干/答案/解析原文完全相同；normalized按现有normalize_stem规则；fingerprint沿用现有题库实现。

## 审核文件

- [geometry_review_batch_01.docx](geometry_review_batch_01.docx)
- [geometry_review_batch_02.docx](geometry_review_batch_02.docx)
- [geometry_review_batch_03.docx](geometry_review_batch_03.docx)
- [geometry_review_batch_04.docx](geometry_review_batch_04.docx)
- [geometry_review_batch_05.docx](geometry_review_batch_05.docx)
- [geometry_review_batch_06.docx](geometry_review_batch_06.docx)
- [geometry_warning_candidates_review.docx](geometry_warning_candidates_review.docx)
- [geometry_unlinked_assets_review.docx](geometry_unlinked_assets_review.docx)

## 决策与数据

- 决策文件：E:/Projects/math_ai/data/question_bank/review_decisions/geometry_review_decisions.jsonl；当前分布：{'pending': 668}。
- 包含261个question和407个asset决策，首次生成全部pending；重复运行不会覆写已有人工决策。
- 几何建议体系为geometry_v1，G001–G010；依据题干目标关键词，不使用来源章节自动指定primary。
- 原始复杂OMML公式直接复制到审核Word作为原文核对材料；未猜测、修补或推导公式/答案。
- 知识总结误识别、复杂题型和来源已有内嵌答案需人工回源确认，未自动删除任何候选。

## 数据库保护

production DB是否修改：**NO**。NO migration / NO import / NO attempts changes。
- 前后哈希：{"E:\\Projects\\math_ai\\math_ai.db": "3c351d7576c5d9b345de1e250129497420cdf83f520d8c83c267dade9be86ab8"}
- V1.1A候选JSONL、原始DOCX及原始图像只读。没有commit。

## 验证

- 8份Word已检查全部图片关系目标、真实media字节、图像比例及最大宽度；原生OMML保留。
- 最终回归：**193 passed in 18.50s**。包含12项审核包测试、原geometry pipeline及DOCX提取测试，以及function_v2、题库验证/审核/导入、掌握度、推荐、训练、多题型、数学公式清理测试。
- 测试命令：`python -X utf8 -m pytest -q tests/test_geometry_review.py tests/test_geometry_pipeline.py tests/test_docx_question_extractor.py tests/test_function_v2.py tests/test_question_validator.py tests/test_question_review.py tests/test_question_importer.py tests/test_mastery.py tests/test_recommendation.py tests/test_training.py tests/test_multi_type.py tests/test_math_formula_cleanup.py`。
- 保存文件复验命令：`python -X utf8 scripts/verify_geometry_review_pack.py`，**PASS**；确认261个ID、六批多图顺序、369个关联图形、38个未关联图形、原73条警告题全保留、668条决策pending及数据库哈希未变。
- `git -c safe.directory=E:/Projects/math_ai diff --check`：通过。
- 生成命令：python -X utf8 scripts/build_geometry_review_pack.py。

## 本阶段新增文件

- `services/geometry_review.py`：审核分组、图形来源/位置核对、角色草标、知识点建议、重复检查、Word生成、pending初始化。
- `scripts/build_geometry_review_pack.py`、`scripts/verify_geometry_review_pack.py`：生成及复验入口。
- `tests/test_geometry_review.py`：12项新增测试，含真实图片嵌入、多图顺序、角色区分、缺图警告、源媒体核对、未关联图形和pending决策。
- `data/question_bank/geometry_v1_1b/`：clean/warning分组、逐题审核元数据、逐图验证、重复报告和汇总JSON。
- `data/question_bank/review_decisions/geometry_review_decisions.jsonl`：全部pending的初始决策文件。
- 本报告与上列8份审核Word。未修改原函数业务代码、原geometry候选数据或真实数据库；原有Git暂存状态保持。

本阶段到此停止，等待人工审核。未进入正式导入或批准。
