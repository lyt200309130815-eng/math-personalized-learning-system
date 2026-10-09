# V1.1C Geometry Production Curation & Import

原261条候选中真实可作答候选：222；rejected_non_question：39；needs_manual_fix：99；duplicate：0；approved/trainable：123。

| 题型 | 正式题数 |
|---|---:|
| single_choice | 60 |
| multiple_choice | 23 |
| fill_blank | 26 |
| subjective | 14 |

| 知识点 | 正式题数 |
|---|---:|
| G001 基本立体图形与表面积体积 | 14 |
| G002 球的切接问题 | 14 |
| G003 空间点线面位置关系 | 19 |
| G004 空间直线、平面的平行 | 21 |
| G005 空间直线、平面的垂直 | 18 |
| G006 空间向量概念与运算 | 8 |
| G007 向量法求空间角 | 8 |
| G008 空间距离 | 1 |
| G009 截面与交线问题 | 12 |
| G010 动态与轨迹问题 | 8 |

difficulty：{'2': 109, '3': 14}；有题干/选项图：45题；只有解析图：35题。

答案泄漏发现：7条，安全分离判断答案到结构化answer；未解决泄漏：0。仍有公式问题：82条真实候选，全部未批准。
原复杂公式没有猜测或补全；安全中间格式通过现有math_normalizer和数学表达式验证。
章节默认映射按§7.1–§7.10；必刷题按真实作答内容。主观题小问共用条件与题图；无源分值题保持未设分值、待人工评阅。
三道图形选项题通过直接目视核查图片A/B/C/D标签修正，未做OCR。

## 正式数据库

- SQLite backup API备份：`E:\Projects\math_ai\backups\math_ai_before_geometry_v1_1c_20261008T150615492884Z.sqlite3`。
- questions：133 → 256；geometry：123。
- attempts：79 → 79；迁移前后每个字段完全一致。
- attempts digest：`1241454b8ece507d949a1f38d2e05025207027dd1676ba42cee3f6507cb7f7ed`（前后一致）。
- DB SHA256 before：`3c351d7576c5d9b345de1e250129497420cdf83f520d8c83c267dade9be86ab8`；after：`8ca580e1ad8104f8ae327178547e6ce8c514fd14165d772bb928de1e571aa0c6`。
- 幂等复验：inserted=0，skipped=123。transaction / foreign_keys=ON / failure rollback。
- 原函数题池与备份逐对象比对一致；旧questions和历史attempts未重写。

## 图像与专题

- 正式图像保存在data/question_assets/images/geometry；批准预览实际嵌入133张图。数据库仅保存path/reference，无BLOB。
- 原38个未关联图形分类：{'decorative': 20, 'unknown': 18}；均保持unlinked/ignored，无自动attach。
- 题干图与选项图在作答前显示；解析图只在提交后查看解析时显示。缺失/损坏必需题图会跳过并记录log。
- 首页/侧栏专题选择：函数、立体几何与空间向量。诊断、训练、画像、推荐、反馈按taxonomy隔离。

## 真实网页验收

- 隐藏Streamlit + headless Edge：PASS。使用真实应用页面和SQLite副本，真实attempts不写测试数据。
- 连续完成15题：{'single_choice': 5, 'fill_blank': 6, 'multiple_choice': 2, 'subjective': 2}；覆盖['G001', 'G002', 'G003', 'G004', 'G005', 'G006', 'G007', 'G008', 'G009', 'G010']。
- 无图选择、有图选择、填空、主观、多图和只有解析图六个场景全部通过；图像实际加载成功、提交前无解析图、提交后正确显示。
- 没有待核标记、raw asset id、raw OMML、KaTeX error。截图及日志：E:\Projects\math_ai\tmp\geometry_browser_20261008T150351975965Z
- 切回函数后的首次诊断、训练、画像、推荐、AI反馈页面均通过；未调用付费API，反馈验收使用规则式反馈。

## 文件与运行记录

- 预览：[geometry_production_approved_preview.docx](geometry_production_approved_preview.docx)。
- 筛选汇总：[geometry_production_candidate_summary.md](geometry_production_candidate_summary.md)。
- 详细迁移/验收证据：geometry_production_import.json、geometry_browser_validation.json、geometry_v1_1c_production_validation.json。
- 正式批准数据：data/question_bank/approved/geometry_v1_1c_approved.jsonl；逐题拒绝/待修复理由与answer_leak_audit位于data/question_bank/geometry_v1_1c。
- 新增services/geometry_curation.py、services/question_assets.py、database/geometry.py、tests/test_geometry_production.py及curate/import/finalize/smoke脚本。
- 修改settings、专题入口及页面、数据库版本过滤、diagnostic/adaptive_training/recommendation/feedback/question_renderer；保持函数旧版兼容。
- 已执行curate_geometry_production、import_geometry_production --apply-production、smoke_geometry_browser、finalize_geometry_production。
- 正式导入前全量测试：463 passed in 96.16s；正式导入后的最终回归：464项全部通过，耗时83.550秒，日志tmp/geometry_final_regression.log。
- 本次收尾修改pages/training.py：重试按钮使用回调，在页面渲染前更新状态，修复错因控件移除后重试作答的AppTest状态错误；相关8项测试通过。README补充V1.1C使用说明，验收JSON补齐最终回归证据。新增两份测试日志，未新增业务模块。
- 本次执行python -X utf8 -m unittest discover -s tests -q、针对test_variation_training.py的离线回归、正式库只读完整性复核、git status --short及git diff --check。正式库复核256题、79条作答，历史摘要不变，外键无违规；diff检查通过（仅行尾转换提示）。
- 未开始OCR，未引入其他章节，未commit。
