# V1.0D.3 多题型诊断与自适应训练

## 原因与修改

诊断原来显式过滤 `single_choice`，页面固定 radio A/B/C/D，提交用单个字母比较。旧诊断持久化题池会在刷新后继续恢复单选题。自适应训练低掌握度选择类权重80%，85%以下主观题权重为0；难度上限与已有曝光还会把非选择题排出可用池。数据库批准题查询和推荐查询已经支持四题型，没有选择题独占过滤。

诊断现在从 function_v2 approved 四题型中规划18题，先保证主要知识点覆盖，再寻找可达到的6/2/7/3配额。题量不足时保留覆盖说明，不补造题目。题型配额的确定性规划与作答后的前置失败分析、未评估知识点优先、难度排序结合。旧未完成诊断通过事务刷新剩余题池，保留已提交答案与 attempts；已完成诊断历史快照保持原样。

两页面复用 question_renderer，分别显示 radio、checkbox、无选项输入框、多行文本与图片上传。诊断填空复用 answer_evaluator；多选比较集合，不依赖顺序。诊断结果区分确定性自动评分和待评阅提交，待评阅不妨碍完成测评。

训练仍由 recommendation 决定学习知识点，由 adaptive_training 综合题型缺口、难度、前置条件及曝光选题。新增会话题型统计及覆盖限制，优先未做过题，再较早做过题。优先规避最近30道题，并按 source/variant fingerprint 和来源段落关联去重。基本难度题耗尽且至少有两次有效证据、掌握度≥40%时，可使用满足前置条件的相邻D3新题；这是选题降级，不会因待评阅提交而改变建议难度。仍不放宽到D4/D5。

## 目标权重

| 掌握度 | 选择类（单选+多选） | 填空 | 解答 |
| --- | ---: | ---: | ---: |
| 未评估 / <40% | 50% | 40% | 10% |
| 40%–70% | 35% | 45% | 20% |
| 70%–85% | 25% | 45% | 30% |
| ≥85% | 20% | 35% | 45% |

权重通过会话累计缺口确定下一题，不使用随机或按ID取首题。可用时单选/多选分担选择类权重；短会话预留填空，高掌握度尝试安排解答。同题型缺少时优先其他非选择题，再选择题，最后较早已做题。限制记录在 type_coverage_limitation。

## 实际网页验收

启动真实 Streamlit HTTP 服务并使用 Microsoft Edge CDP 操作网页；数据库通过 SQLite backup API复制，入口仅将默认学生编号替换为新测试学生，所有服务、选题和页面与应用一致。未强制指定题目。

| 题型 | 完整18题诊断 | 连续8题训练 |
| --- | ---: | ---: |
| single_choice | 6 | 3 |
| multiple_choice | 2 | 0 |
| fill_blank | 7 | 1 |
| subjective | 3 | 4 |

诊断前4题出现四种题型；选择类44.4%，填空38.9%，覆盖K001–K015。自动评分15题，3题主观待评阅。训练选择类37.5%，包含三种题型，目标K004：该知识点仅1道填空，故无法达到45%填空目标，记录题型/难度覆盖限制。训练4题自动评分、4题待评阅，自动评分正确率50%。大题上传合成PNG成功，数据库只保存文件引用，待评阅保持 correctness/score=NULL；图片未进行OCR。

8题训练没有重复诊断题。主观题提交前后的掌握度与连续正确/错误、建议难度保持不变。确定性判分的 single_choice、multiple_choice、fill_blank 才产生掌握证据；needs_manual_review填空与未评主观题不计有效证据。

详细题目顺序和验收证据见 `v1_0d_3_browser_validation.json`；截图与隔离数据库在其 screenshots_directory 指向的 tmp 目录，均不进入Git。

## 验证与范围

运行 `python -m unittest discover -s tests -q`：396项全部通过。保留原371项覆盖并更新旧题型权重及multiselect断言以匹配新要求，新增25项诊断/训练检查。最终结果见 `v1_0d_3_final_validation.json`。

运行 `python scripts/smoke_diagnostic_adaptive_browser.py` 完成真实网页验收，输出一次 Diagnostic question mix / Adaptive session mix。使用 `git -c safe.directory=E:/Projects/math_ai diff --check` 检查空白，不更改全局Git配置。

本轮新增：`services/diagnostic_mix.py`、`tests/test_multitype_diagnostic_adaptive.py`、浏览器验收脚本及报告。修改：诊断服务/页面、训练服务/页面、题型策略、共享renderer、首页说明及相关既有测试。

正式题库仍133题（单选72、多选20、填空25、解答16）；验收前后真实attempts 47条，摘要 `9549ab292729cb896b2b869bbfe399420ed8f37e44f2ab9b4fccd5917341aa3a` 相同。未扩题、未修改真实历史作答、未运行OCR、未调用LLM评分、未commit。停留在V1.0D.3。
