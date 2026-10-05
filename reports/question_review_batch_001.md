# 第一批金标准题人工审核报告

## 审核进度

候选总数：29
approved：29
rejected：0
skipped/reviewed：0
reviewed remaining：0
其中显式 skip：0；尚未审核：0

尚未人工批准的题不会成为金标准题。跳过不代表拒绝或批准。
批准须核对答案、解析、选项唯一性、定义域、参数边界、难度及主要知识点。
严格策略：非 complete 或有 warning 不允许批准，本阶段不提供 warning 覆盖。
候选快照只读；审核日志为恢复依据，批准文件和本报告可重新生成。

候选 SHA-256：`320069b606b70a6afd31f2a032c127825c64b5da544f96e251f4b656dfe9190d`

## approved 知识点分布

| 知识点 | 数量 |
| --- | ---: |
| K001 函数概念与三要素 | 1 |
| K002 定义域、值域与函数表示 | 3 |
| K003 函数单调性 | 2 |
| K004 函数最值 | 2 |
| K005 函数奇偶性 | 2 |
| K006 周期性与对称性 | 2 |
| K007 二次函数 | 0 |
| K008 幂函数 | 1 |
| K009 指数与指数函数 | 2 |
| K010 对数与对数函数 | 2 |
| K011 指数、对数、幂大小比较 | 3 |
| K012 函数图象与图象变换 | 2 |
| K013 函数零点与方程 | 2 |
| K014 函数与方程综合 | 2 |
| K015 函数模型应用 | 3 |

## approved 难度分布

| difficulty | 数量 |
| --- | ---: |
| 1 | 1 |
| 2 | 18 |
| 3 | 9 |
| 4 | 1 |
| 5 | 0 |

## approved ability_tag 分布

| 标签 | 数量 |
| --- | ---: |
| concept_understanding | 3 |
| calculation | 16 |
| logical_reasoning | 21 |
| graph_analysis | 4 |
| classification_discussion | 0 |
| parameter_analysis | 4 |
| modeling | 3 |

## approved method_tag 分布

| 标签 | 数量 |
| --- | ---: |
| definition | 10 |
| substitution | 4 |
| monotonicity | 9 |
| symmetry | 5 |
| special_value | 3 |
| intermediate_value | 1 |
| graph_transform | 3 |
| zero_analysis | 4 |
| bisection | 1 |
| function_model | 3 |

## 暂无金标准题的知识点

- K007 二次函数：暂无金标准题。

K007 暂无金标准题，需要 Batch 002 定向补充。
其他节点先完成本批审核，完成后仍为0的节点再定向补充。本阶段不处理 Batch 002。

## 数据库边界

不写数据库，不调用 LLM，正式业务未切换到 function_v2。
临时库验收脚本独立运行，自动创建和清理隔离 SQLite，不修改真实 math_ai.db 或 attempts。

## Batch 001 批准结论

用户已完成人工审核，批准记录中的 manual_user 指用户确认，不代表第二次 AI 审核。
Batch 001 可以作为第一批金标准题，但 function_v2 尚不能认为题库覆盖完整。

## V0.8D 隔离集成验证

首次导入：inserted=29；重复导入：inserted=0、skipped=29。reviewed/draft/rejected 共87个变体均被拒绝。

全部167项离线测试通过。训练仅查询 approved，15节点仍沿用确定性 mastery/recommendation 算法；core 和 question prerequisite 均检查，近期题去重，无题返回友好覆盖不足状态。related 不重复计证据，旧 Q005/Q006 不污染新 K005。训练、画像和规则反馈页面 AppTest 通过，不调用 LLM。

验收作用域内才启用15节点查询适配，真实应用尚未迁移；临时数据库自动删除，不复制真实学生数据。

Real math_ai.db modified: NO

Real attempts modified: NO

数据库 SHA-256（前后相同）：`6fce74ab6f7482c1e512778fb72e2b63919bfc9cb0a8afa43d6f4e7288b5393f`。真实 attempts 仍为7条，内容摘要前后相同。原候选快照 SHA-256 也保持一致。
