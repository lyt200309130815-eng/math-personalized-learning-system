# 第二批金标准题人工审核报告

## 审核进度

候选总数：26
approved：26
rejected：0
skipped/reviewed：0
reviewed remaining：0
其中显式 skip：0；尚未审核：0

尚未人工批准的题不会成为金标准题。跳过不代表拒绝或批准。
批准须核对答案、解析、选项唯一性、定义域、参数边界、难度及主要知识点。
严格策略：非 complete 或有 warning 不允许批准，本阶段不提供 warning 覆盖。
候选快照只读；审核日志为恢复依据，批准文件和本报告可重新生成。

候选 SHA-256：`cbccf1d5b5663852a09e25ba15749796c4e6283acf26cc247487755549bddad6`

## approved 知识点分布

| 知识点 | 数量 |
| --- | ---: |
| K001 函数概念与三要素 | 1 |
| K002 定义域、值域与函数表示 | 0 |
| K003 函数单调性 | 3 |
| K004 函数最值 | 3 |
| K005 函数奇偶性 | 3 |
| K006 周期性与对称性 | 3 |
| K007 二次函数 | 0 |
| K008 幂函数 | 2 |
| K009 指数与指数函数 | 0 |
| K010 对数与对数函数 | 2 |
| K011 指数、对数、幂大小比较 | 0 |
| K012 函数图象与图象变换 | 3 |
| K013 函数零点与方程 | 3 |
| K014 函数与方程综合 | 3 |
| K015 函数模型应用 | 0 |

## approved 难度分布

| difficulty | 数量 |
| --- | ---: |
| 1 | 3 |
| 2 | 7 |
| 3 | 10 |
| 4 | 6 |
| 5 | 0 |

## approved ability_tag 分布

| 标签 | 数量 |
| --- | ---: |
| concept_understanding | 8 |
| calculation | 17 |
| logical_reasoning | 17 |
| graph_analysis | 4 |
| classification_discussion | 2 |
| parameter_analysis | 7 |
| modeling | 0 |

## approved method_tag 分布

| 标签 | 数量 |
| --- | ---: |
| definition | 8 |
| substitution | 10 |
| monotonicity | 6 |
| symmetry | 5 |
| special_value | 8 |
| intermediate_value | 2 |
| graph_transform | 3 |
| zero_analysis | 3 |
| bisection | 2 |
| function_model | 0 |

## 暂无金标准题的知识点

以下仅表示Batch 002本批没有对应题，不代表Batch 001与Batch 002合并题库的覆盖情况；合并统计见原创补缺覆盖预测报告。

- K002 定义域、值域与函数表示：暂无金标准题。
- K007 二次函数：暂无金标准题。
- K009 指数与指数函数：暂无金标准题。
- K011 指数、对数、幂大小比较：暂无金标准题。
- K015 函数模型应用：暂无金标准题。

K007 暂无金标准题，将由待人工审核的原创题定向补缺。
本批26题由用户人工确认批准；后续原创题保持 reviewed，不自动批准。

## 数据库边界

不写数据库，不调用 LLM，正式业务未切换到 function_v2。
临时库验收脚本独立运行，自动创建和清理隔离 SQLite，不修改真实 math_ai.db 或 attempts。

## Batch 002 批准结论

用户已完成人工审核，批准记录中的 manual_user 指用户确认，不代表第二次 AI 审核。
Batch 002 可以作为第二批金标准题，但 function_v2 尚不能认为题库覆盖完整。
