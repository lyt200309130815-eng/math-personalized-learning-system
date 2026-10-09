# V1.1D Geometry Coverage Balancing & Adaptive Quality Improvement

本轮完成离线覆盖审计、原资料恢复和自适应质量检查，停在人工审核。未批准、未导入、未修改正式题目或学生记录。

## A. 正式覆盖复核

geometry_v1正式trainable为123题，正式数据库总题数256；题型为单选60、多选23、填空26、主观14；D2=109、D3=14，D1/D4/D5为空。
完整交叉表见[覆盖审计](geometry_v1_1d_coverage_audit.md)。

| 知识点 | 当前正式 | 本轮恢复待审 | 全部通过后潜在题数 |
|---|---:|---:|---:|
| G001 基本立体图形与表面积体积 | 14 | 22 | 36 |
| G002 球的切接问题 | 14 | 8 | 22 |
| G003 空间点线面位置关系 | 19 | 8 | 27 |
| G004 空间直线、平面的平行 | 21 | 6 | 27 |
| G005 空间直线、平面的垂直 | 18 | 9 | 27 |
| G006 空间向量概念与运算 | 8 | 19 | 27 |
| G007 向量法求空间角 | 8 | 22 | 30 |
| G008 空间距离 | 1 | 7 | 8 |
| G009 截面与交线问题 | 12 | 5 | 17 |
| G010 动态与轨迹问题 | 8 | 7 | 15 |

V1.1C及本轮初查attempts为79；工作期间运行中的S001练习页面产生新增作答，最终只读复核为94。原79条每个字段的摘要与迁移前一致；正式库中本轮V1_1D测试学生attempts=0。新记录全部保留。

## B. 99条待修复候选的结果

98条原候选恢复成功、1条仍不明确。原候选存在合并多道独立练习的情况：只在这99条的原DOCX范围内按明确小题起点、独立答案和解析分段，共得到113道独立待审题；另排除1段知识总结。没有新增外部题或原创题。
99条互斥主分类：{"recoverable_formula": 40, "recoverable_structure": 57, "recoverable_asset": 1, "still_ambiguous": 1, "non_question": 0}
恢复题可能同时涉及公式、结构、图形修复；修复类型计数（可重叠）：{"recoverable_formula": 90, "recoverable_structure": 72, "recoverable_asset": 28}
逐原候选记录：data/question_bank/geometry_v1_1d/recovery_analysis.jsonl；逐独立题及定位：recovery_question_details.jsonl。

## C. 恢复题型

单选44、多选14、填空25、主观30，共113道。主观题比原正式题库14道增加了30道待审过程题，保留原小问与源分值，无源分值不推算。

## D–E. 知识点分布与G008补强

本轮G001–G010分布见上表。G008恢复7题；未来全部批准后可由1达到8，尚距10题目标差2题。§7.8中的纯空间角/探索题改按实际任务标注，不用章节名称虚增G008。
| G008源题 | 内容 | 题型 | 建议难度 |
|---|---|---|---|
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx · 2. | 点到直线距离 | single_choice | D3 |
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx · 3. | 点到平面/距离综合 | single_choice | D3 |
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx · 例1 | 点到直线距离 | subjective | D3 |
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx · 例2 | 点到平面/距离综合 | fill_blank | D4 |
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx · 跟踪训练1 | 点到直线与点到平面距离综合 | multiple_choice | D3 |
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx · 1. | 点到直线与点到平面距离综合 | subjective | D4 |
| 第七章　必刷小题13　立体几何.docx · 8. | 点到平面/距离综合 | single_choice | D3 |

G008待审题为选择类4、填空1、主观2；加上原正式填空1后有选择类4/填空2/主观2。新增G008难度为D3五题、D4两题，原正式D2一题。达到8题但仍不满足长期每点10题目标。

## F. 难度校准与剩余梯度缺口

恢复题待确认难度：D1=4、D2=22、D3=60、D4=23、D5=4。
V1.1C客观题统一D2、主观题统一D3，确实是题型占位值；本轮以原解答方法、推理步骤、数学目标与探索/参数任务生成逐题建议和证据。难度标准见覆盖审计，所有建议须由人工确认，不按数量目标机械升档。
123道正式题的校准草案分布：{"2": 44, "3": 65, "1": 6, "4": 8}；仅写入approved_difficulty_proposals.jsonl，没有改变正式difficulty。

| 知识点 | 新D2 | 新D3 | 新D4 | 新D5 | 新主观题 |
|---|---:|---:|---:|---:|---:|
| G006 | 6 | 8 | 4 | 0 | 4 |
| G007 | 0 | 9 | 10 | 3 | 12 |
| G008 | 0 | 5 | 2 | 0 | 2 |
| G009 | 2 | 0 | 2 | 0 | 1 |
| G010 | 0 | 6 | 0 | 1 | 1 |

G007/G008仍缺新增D2，G009缺新增D3，G010缺新增D2/D4；结合正式题后也不强行宣称各点完整覆盖。后续只能继续审核现有可靠源题，不原创凑数。

## G. 仍无法可靠恢复的内容

1条原候选（GQ-50a2466ead939ff28bd5，必刷小题13第6题）：原DOCX用GBK_S特殊符号字体存储“綉”。Unicode文本无法可靠确认其数学含义，不能猜成等号或平行符号；保留formula_warning / needs_manual_fix，不进入审核成功包。
其他原OMML支持的向量箭头、圆弧标记、分式、根式、上下标、矩阵/方程组和定界符按结构恢复；未知节点、缺失主体/度数、符号字体继续阻断。此规则也有负向测试。

## H. 二次审核包

[geometry_recovery_batch_001_可读版.docx](geometry_recovery_batch_001_可读版.docx)
只包含113道本轮成功恢复题，不要求重新审核原261题。逐题包含题干、题图、选项/答案、解析、知识点、建议难度及依据、来源文件/题号/段落、修复说明，并附原DOCX原生数学段落（保留Word样式上下标）。
Word实际嵌入180张图；待审JSONL：data/question_bank/geometry_v1_1d/geometry_recovery_batch_001.jsonl。全部quality_status=reviewed、review_status=pending_review、trainable=false。

## 自适应、诊断与曝光检查

目标知识点仍由掌握度与递归前置检查决定，不按题量最多选目标；题内选择继续考虑掌握度、难度、题型缺口、近期曝光与覆盖可用性。几何难度偏好为低掌握/少独立证据D1/D2、中等D2/D3、较高D3/D4、稳定且至少6道独立原题证据D4/D5；缺题明确coverage limitation，不把D2当成高阶证据。待评主观作答仍不改变掌握度。
正式库当前没有D4/D5，实际进阶只能报告覆盖不足；测试副本中加入仅用于测试的不同难度题，验证高掌握可选D4、连续正确后可选D5，低掌握不会越级。
几何首次诊断默认15题，规划覆盖G001–G010，题库不足时说明提前结束；G008仅有原题若最近30题曝光则跳过，不反复探测。少于3道独立有效原题证据显示“证据不足 / 待进一步训练”，不展示0%掌握度，不改变原A/R/S/D数值模型。
source_fingerprint按原文件及起始段落稳定生成，配合原段落范围、内容指纹识别跨版本/跨源复制；同session不重复，最近30道不同题及训练曝光优先回避。纯近期重复的几何池停止并报告覆盖不足。
question_diagram / option_image仍为作答前图，solution_diagram只在提交后解析区显示；恢复后按明确源段落重新分配角色，未绑定未关联图片。

## I. 是否修改production DB

**NO。** 本轮只读正式库，未批准、未导入、未运行production migration，也未写S001测试作答。函数正式题池与原79条作答摘要复核保持，所有新自动作答使用临时SQLite副本。SQLite WAL模式下主文件SHA不能替代逻辑快照，本轮同时比较questions/attempts逐字段逻辑快照及函数题池。

## J. 自动测试与渲染验收

全量504项全部通过，耗时105.264秒；原464项包含在内，新增40项。日志：tmp/geometry_v1_1d_final_tests.log。
真实无窗口Edge渲染：113题，3099处数学片段，KaTeX错误0；题图68、解析图112，解析图作答前0，图像均实际加载。报告：geometry_v1_1d_browser_validation.json。
包含正式SQL交叉核对、G008缺口、D1–D5规则、不可恢复公式/字体阻断、图像保留与防泄漏、去重/指纹、源练习拆分、函数隔离、真实Streamlit页面证据不足与覆盖提示、测试学生隔离。

## 文件和命令

新增services/geometry_quality.py、services/geometry_recovery.py、services/source_extractors/geometry_math.py、tests/test_geometry_quality.py、recover_geometry_batch.py、smoke_geometry_recovery.py、report_geometry_quality.py；新增本阶段JSONL/扫描与汇总、覆盖审计、审核Word、浏览器及最终验收报告。
修改database/database.py、services/adaptive_training.py、diagnostic.py、mastery.py、recommendation.py、profile.py、math_normalizer.py、geometry_curation.py、geometry_review.py、source_extractors/docx_question_extractor.py及训练/诊断/推荐页面；README补充本阶段说明。question_renderer已重读及回归验证，本轮保留其图像显示契约。
执行：python -X utf8 scripts/recover_geometry_batch.py；python -X utf8 -m unittest discover -s tests -p test_geometry_quality.py -q；python -X utf8 -m unittest discover -s tests -q；python -X utf8 scripts/smoke_geometry_recovery.py；python -X utf8 scripts/report_geometry_quality.py；只读数据库复核；git status --short与git diff --check。
未做OCR、未联网找题、未扩展章节、未重构基础架构、未commit。下一步仅人工审核此113题包及难度建议；确认前停止。
