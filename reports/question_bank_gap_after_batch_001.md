# Batch 001 金标准题覆盖与 Batch 002 缺口分析

仅分析缺口，没有提取或生成 Batch 002，不修改 mastery、数据库或学生数据。
建议门槛：每节点至少3道 approved，至少1道难度1–2、至少1道难度2–3；同一道难度2题可满足两类难度条件。
P0 无题；P1 少于3题；P2 缺基础诊断题；P3 缺巩固题；P4 后续才考虑难度4–5。并列按知识点ID排序。
coverage 状态只评价题库覆盖，不代表学生能力。

整体状态：insufficient_coverage

| 知识点 | approved | d1 | d2 | d3 | d4 | d5 | 状态 | 优先级/缺口 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| K001 函数概念与三要素 | 1 | 0 | 0 | 1 | 0 | 0 | insufficient_coverage | P1 / P1,P2 |
| K002 定义域、值域与函数表示 | 3 | 0 | 2 | 1 | 0 | 0 | sufficient_coverage | P4 / 基础门槛已满足 |
| K003 函数单调性 | 2 | 0 | 1 | 1 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K004 函数最值 | 2 | 0 | 2 | 0 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K005 函数奇偶性 | 2 | 0 | 0 | 2 | 0 | 0 | insufficient_coverage | P1 / P1,P2 |
| K006 周期性与对称性 | 2 | 0 | 2 | 0 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K007 二次函数 | 0 | 0 | 0 | 0 | 0 | 0 | insufficient_coverage | P0 / P0,P1,P2,P3 |
| K008 幂函数 | 1 | 0 | 1 | 0 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K009 指数与指数函数 | 2 | 1 | 1 | 0 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K010 对数与对数函数 | 2 | 0 | 2 | 0 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K011 指数、对数、幂大小比较 | 3 | 0 | 3 | 0 | 0 | 0 | sufficient_coverage | P4 / 基础门槛已满足 |
| K012 函数图象与图象变换 | 2 | 0 | 2 | 0 | 0 | 0 | insufficient_coverage | P1 / P1 |
| K013 函数零点与方程 | 2 | 0 | 0 | 2 | 0 | 0 | insufficient_coverage | P1 / P1,P2 |
| K014 函数与方程综合 | 2 | 0 | 0 | 1 | 1 | 0 | insufficient_coverage | P1 / P1,P2 |
| K015 函数模型应用 | 3 | 0 | 2 | 1 | 0 | 0 | sufficient_coverage | P4 / 基础门槛已满足 |

## 建议补题顺序

K007 → K001 → K003 → K004 → K005 → K006 → K008 → K009 → K010 → K012 → K013 → K014 → K002 → K011 → K015

先补 K007 二次函数（P0），再按 P1/P2/P3 缺口补足已有节点。P4 表示后续扩展，不优先于基础覆盖。
K007 当前 approved=0；Batch 001 可作为首批金标准题，function_v2 题库覆盖尚不完整。
