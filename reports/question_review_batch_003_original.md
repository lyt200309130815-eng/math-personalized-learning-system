# 第三批原创金标准题人工审核报告

## 审核进度

候选总数：11
approved：11
rejected：0
skipped/reviewed：0
reviewed remaining：0
其中显式 skip：0；尚未审核：0

尚未人工批准的题不会成为金标准题。跳过不代表拒绝或批准。
批准须核对答案、解析、选项唯一性、定义域、参数边界、难度及主要知识点。
严格策略：非 complete 或有 warning 不允许批准，本阶段不提供 warning 覆盖。
候选快照只读；审核日志为恢复依据，批准文件和本报告可重新生成。

候选 SHA-256：`f40b4fc5bd93cf2f099b55ba6dc9d0171c2ddb12caf9408335cd6d531d4d4782`

## approved 知识点分布

| 知识点 | 数量 |
| --- | ---: |
| K001 函数概念与三要素 | 2 |
| K002 定义域、值域与函数表示 | 0 |
| K003 函数单调性 | 0 |
| K004 函数最值 | 0 |
| K005 函数奇偶性 | 1 |
| K006 周期性与对称性 | 0 |
| K007 二次函数 | 5 |
| K008 幂函数 | 0 |
| K009 指数与指数函数 | 2 |
| K010 对数与对数函数 | 0 |
| K011 指数、对数、幂大小比较 | 0 |
| K012 函数图象与图象变换 | 0 |
| K013 函数零点与方程 | 0 |
| K014 函数与方程综合 | 1 |
| K015 函数模型应用 | 0 |

## approved 难度分布

| difficulty | 数量 |
| --- | ---: |
| 1 | 4 |
| 2 | 6 |
| 3 | 1 |
| 4 | 0 |
| 5 | 0 |

## approved ability_tag 分布

| 标签 | 数量 |
| --- | ---: |
| concept_understanding | 8 |
| calculation | 3 |
| logical_reasoning | 4 |
| graph_analysis | 5 |
| classification_discussion | 0 |
| parameter_analysis | 0 |
| modeling | 0 |

## approved method_tag 分布

| 标签 | 数量 |
| --- | ---: |
| definition | 8 |
| substitution | 3 |
| monotonicity | 0 |
| symmetry | 2 |
| special_value | 3 |
| intermediate_value | 0 |
| graph_transform | 0 |
| zero_analysis | 1 |
| bisection | 0 |
| function_model | 0 |

## 暂无金标准题的知识点

- K002 定义域、值域与函数表示：暂无金标准题。
- K003 函数单调性：暂无金标准题。
- K004 函数最值：暂无金标准题。
- K006 周期性与对称性：暂无金标准题。
- K008 幂函数：暂无金标准题。
- K010 对数与对数函数：暂无金标准题。
- K011 指数、对数、幂大小比较：暂无金标准题。
- K012 函数图象与图象变换：暂无金标准题。
- K013 函数零点与方程：暂无金标准题。
- K015 函数模型应用：暂无金标准题。

K007 已有金标准题。
其他节点先完成本批审核，完成后仍为0的节点再定向补充。本阶段不开始新批次。

## 数据库边界

不写数据库，不调用 LLM，正式业务未切换到 function_v2。
临时库验收脚本独立运行，自动创建和清理隔离 SQLite，不修改真实 math_ai.db 或 attempts。

## Batch 003 original 批准结论

用户已完成人工审核，批准记录中的 manual_user 指用户确认，不代表第二次 AI 审核。
Batch 003 original 可以作为第三批原创金标准题，但 function_v2 尚不能认为题库覆盖完整。
