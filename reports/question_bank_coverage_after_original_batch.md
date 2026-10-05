# 原创补缺题覆盖预测

Batch 001 approved=29；Batch 002 approved=26；Batch 003 original reviewed=11。当前正式批准55题；原创题尚未人工批准。
projected_total仅是假设原创题未来全部批准后的覆盖预测，不用于正式训练，也不修改mastery。
门槛：每节点至少3题、至少1道难度1–2、至少1道难度2–3；难度2可同时满足两类要求。

| 知识点 | Batch001 approved | Batch002 approved | Batch003 reviewed | current_approved | new_reviewed | projected_total | 当前状态 | 预测状态 |
|---|---:|---:|---:|---:|---:|---:|---|---|
| K001 函数概念与三要素 | 1 | 1 | 2 | 2 | 2 | 4 | insufficient_coverage | sufficient_coverage |
| K002 定义域、值域与函数表示 | 3 | 0 | 0 | 3 | 0 | 3 | sufficient_coverage | sufficient_coverage |
| K003 函数单调性 | 2 | 3 | 0 | 5 | 0 | 5 | sufficient_coverage | sufficient_coverage |
| K004 函数最值 | 2 | 3 | 0 | 5 | 0 | 5 | sufficient_coverage | sufficient_coverage |
| K005 函数奇偶性 | 2 | 3 | 1 | 5 | 1 | 6 | insufficient_coverage | sufficient_coverage |
| K006 周期性与对称性 | 2 | 3 | 0 | 5 | 0 | 5 | sufficient_coverage | sufficient_coverage |
| K007 二次函数 | 0 | 0 | 5 | 0 | 5 | 5 | insufficient_coverage | sufficient_coverage |
| K008 幂函数 | 1 | 2 | 0 | 3 | 0 | 3 | sufficient_coverage | sufficient_coverage |
| K009 指数与指数函数 | 2 | 0 | 2 | 2 | 2 | 4 | insufficient_coverage | sufficient_coverage |
| K010 对数与对数函数 | 2 | 2 | 0 | 4 | 0 | 4 | sufficient_coverage | sufficient_coverage |
| K011 指数、对数、幂大小比较 | 3 | 0 | 0 | 3 | 0 | 3 | sufficient_coverage | sufficient_coverage |
| K012 函数图象与图象变换 | 2 | 3 | 0 | 5 | 0 | 5 | sufficient_coverage | sufficient_coverage |
| K013 函数零点与方程 | 2 | 3 | 0 | 5 | 0 | 5 | sufficient_coverage | sufficient_coverage |
| K014 函数与方程综合 | 2 | 3 | 1 | 5 | 1 | 6 | insufficient_coverage | sufficient_coverage |
| K015 函数模型应用 | 3 | 0 | 0 | 3 | 0 | 3 | sufficient_coverage | sufficient_coverage |

当前不足门槛：K001、K005、K007、K009、K014
预测不足门槛：无

## 原创题难度分布

{1: 4, 2: 6, 3: 1}

真实数据库未迁移；原创题没有批准，也没有导入任何数据库。
