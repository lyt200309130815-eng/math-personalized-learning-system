# 函数知识体系与题库迁移方案（V0.8A）

## 状态与适用范围

本文件是待教师审阅的设计，不是迁移脚本。体系版本拟为 `function_v2`；旧体系称 `function_v1`。当前只覆盖高中“函数”，不生成、导入题目，不修改数据库、attempts 或服务代码。

V0.8A 设计时仅检查了6道种子题；V0.8B 已发现并有限提取 `data/raw_sources/function/` 中15份 DOCX。实际来源路径与哈希见 `data/source_mapping.json`，首批提取结果见 `reports/question_import_batch_001.md`。这不代表全文或数学答案已经审核；版本未知时保留 null，以 XML 段落定位，不编造页码。核心知识图与迁移方案保持设计状态，真实数据库尚未迁移。

## 核心知识点与直接前置图

前置编号表示所有直接前置都需要满足；传递前置由图递归取得。图无循环、没有自引用。编号仅为标识，不是固定教学顺序：例如 K007 二次函数与 K008 幂函数是并行分支。前置只列必要基础，不把所有相关知识强制串成一条链。K002 的基础值域不强制依赖 K004；复杂值域题另外标注相关知识。集合、实数运算等属于教师确认的入门基础，本版本不新建非函数知识点。

| 编号 / 名称 | 定义与边界 | 直接前置 | 典型题型 | 常见错误 | ability_tag | method_tag |
| --- | --- | --- | --- | --- | --- | --- |
| K001 函数概念与三要素 | 对应关系、唯一性，定义域、对应法则、值域的含义及函数相等；三要素的具体求解归 K002 | 无 | 判断函数关系；判断两函数是否相同 | 忽略定义域；把一对多当函数；混淆函数值与函数 | concept_understanding, logical_reasoning | definition, special_value |
| K002 定义域、值域与函数表示 | 常见表达式的定义域、基础值域；解析式、列表、图象及分段表示 | K001 | 根式/分式定义域；由对应关系求值域；分段函数求值 | 忘记分母非零；区间端点错；混淆定义域和值域；漏分段条件 | concept_understanding, calculation, logical_reasoning | definition, substitution, special_value |
| K003 函数单调性 | 指定区间上的增减定义、判断、证明与应用；不能把分离区间自动合并 | K002 | 比较函数值；判单调区间；单调性求参数范围 | 不注明区间；不等式方向错；将各段递增误作整体递增 | logical_reasoning, graph_analysis, parameter_analysis | definition, monotonicity, special_value |
| K004 函数最值 | 在指定定义域上求最大/最小值，区分最值与取不到的界；涉及复杂值域时联标 K002 | K002 | 端点/内部候选比较；闭区间最值；恒成立参数条件 | 漏端点；候选点不在定义域；把上界当最大值 | calculation, logical_reasoning, classification_discussion, parameter_analysis | monotonicity, substitution, special_value |
| K005 函数奇偶性 | 定义域关于原点对称与 f(-x)=±f(x)，性质判断、证明和应用 | K002 | 奇偶判断；补全表达式或图象；参数限制 | 只代入等式不查定义域；把既奇又偶情况排除；符号错 | concept_understanding, logical_reasoning, graph_analysis, parameter_analysis | definition, substitution, symmetry, special_value |
| K006 周期性与对称性 | 正周期、最小正周期存在性；轴/中心对称及函数关系式推断，不将奇偶性与所有对称性等同 | K002 | 周期求值；由 f(x+a)=f(x) 研究周期；平移对称轴/中心 | 把任意周期当最小正周期；平移符号错；忽略定义域闭合性 | logical_reasoning, graph_analysis, calculation | definition, substitution, symmetry, special_value |
| K007 二次函数 | 二次函数解析式、顶点、对称轴、区间增减和最值；二次方程零点归 K013 | K001, K002 | 配方；区间最值；给定条件求解析式；顶点含参数分类 | 顶点横坐标符号错；漏开口方向；不比较端点 | calculation, graph_analysis, classification_discussion, parameter_analysis | substitution, monotonicity, symmetry, special_value |
| K008 幂函数 | 高中范围常见幂函数及其定义域、图象、性质；不泛化任意实指数定义 | K001, K002 | 辨认幂函数；给定幂指数分析性质；基础比较 | 混淆系数与幂指数；负数底数合法性错；奇偶指数混淆 | concept_understanding, calculation, graph_analysis | definition, monotonicity, symmetry, special_value |
| K009 指数与指数函数 | 指数运算、a^x 的定义与性质，a>0 且 a≠1，区分 a>1 与 0<a<1 | K001, K002 | 指数化简；底数分类；图象识别；指数式大小 | 漏底数条件；指数法则错误；底数小于1时方向错 | calculation, logical_reasoning, graph_analysis, classification_discussion | definition, substitution, monotonicity, special_value |
| K010 对数与对数函数 | 对数定义、运算和图象；底数条件及真数正性，与指数形式互化 | K002, K009 | 对数运算；定义域；底数分类；指数对数互化 | 真数未检查；把和的对数拆成对数和；底数条件错 | concept_understanding, calculation, logical_reasoning, classification_discussion | definition, substitution, monotonicity, special_value |
| K011 指数、对数、幂大小比较 | 利用单调性、同底/同指数、特殊中间值比较合法表达式 | K008, K009, K010 | 三数排序；跨类型比较；含参数比较 | 直接比较不同底数；选错中间值；忽略定义条件 | logical_reasoning, calculation, classification_discussion | monotonicity, special_value, substitution |
| K012 函数图象与图象变换 | 从图象读性质；平移、伸缩、翻折、绝对值变换；具体函数族需联标相应知识点 | K002 | 图象匹配；f(x+a)、af(x) 变换；绝对值图象 | 左右平移方向错；横纵伸缩混淆；翻折范围错 | graph_analysis, logical_reasoning, calculation | graph_transform, symmetry, special_value |
| K013 函数零点与方程 | 零点与方程解的对应、存在性与个数、连续条件下零点存在性及二分法 | K002 | 求/估计零点；图象交点个数；二分区间 | 忽略连续条件；把异号条件当唯一性；混淆零点与点坐标 | logical_reasoning, graph_analysis, calculation | zero_analysis, intermediate_value, bisection, monotonicity |
| K014 函数与方程综合 | 综合图象、零点、增减和最值处理方程、不等式与参数讨论；具体函数族另联标 | K013 | 参数下根的个数；恒成立；分段/复合函数综合 | 漏参数边界；重根重复计数；分类不全；转化不等价 | logical_reasoning, classification_discussion, parameter_analysis, graph_analysis | zero_analysis, monotonicity, substitution, special_value |
| K015 函数模型应用 | 从情境建变量关系、选函数模型、限定实际定义域并解释和检验结果 | K002 | 增长模型；成本收益；分段计费；现实最优化 | 单位错；忽视整数/非负限制；模型选择无依据；不解释结论 | modeling, calculation, logical_reasoning, graph_analysis | function_model, substitution, monotonicity, special_value |

核心前置只表示进入该知识点真正必要的基础，不要求事先掌握所有典型解法。K004 同样改为 K002：理解最值不必须先掌握单调性，使用单调性求最值的题再加 K003。K006 不强制奇偶性；K007/K008/K009 可在函数概念与表示之后进入基础学习。K010 保留 K009，并明确 K002 的定义域基础。K013 基础零点与方程对应只需 K002，唯一性证明和图象交点题分别加 K003/K012；连续条件作为题意和方法适用条件检查。K014 的核心只保留 K013，最值、图象和函数族依赖逐题确定。K015 的基础建模只需 K002，不能把所有模型类型的知识叠加为统一门槛。K011 保留三类函数知识，是该跨类型比较单元的对象基础；单调性比较法另加题级 K003。

### 题级前置设置示例（仅规则，不新增题目）

| 主要知识点 | 题目实际使用的必要背景 | question_prerequisites |
| --- | --- | --- |
| K004 | 单调性求最值 | K003 |
| K006 | 奇偶性推导周期或对称关系 | K005 |
| K007 | 单调性或最值综合应用 | 按题选择 K003 / K004；基础配方、顶点识别不加 |
| K008 | 幂函数单调性 / 奇偶性 | 分别选择 K003 / K005，不统一强制两项 |
| K009、K010、K011 | 单调性证明或比较 | K003 |
| K012 | 奇偶性 / 周期与对称关系 | 按题选择 K005 / K006；一般平移不需要 |
| K013 | 零点唯一性 / 图象交点分析 | 按题选择 K003 / K012；基础零点判断不需要 |
| K014 | 增减、最值、图象或具体函数族综合 | 按题选择 K003、K004、K012、K007–K010 中真正必要的项 |
| K015 | 最优化 / 二次模型 / 指数模型 | 分别按题选择 K004 / K007 / K009；基础分段计费不强制 |

上表是按解法选择的规则，不是把所有列出的节点无条件合并。`source_mapping.json` 的 `question_prerequisite_rules` 记录同样的条件；已有6题的 primary/related 和额外 K007 映射保持不变。

## 标签词表与题目映射规则

能力标签仅允许以下 7 项，不作为知识点，也不等于错误类型：

| ability_tag | 含义 |
| --- | --- |
| concept_understanding | 识别概念、条件与适用边界 |
| calculation | 完成合法且准确的运算 |
| logical_reasoning | 根据定义与性质建立推理链 |
| graph_analysis | 读取、比较、解释图象 |
| classification_discussion | 按必要条件分类并覆盖边界 |
| parameter_analysis | 分析参数对定义域、性质、图象、零点等的影响 |
| modeling | 把情境转化为函数模型并解释结果 |

方法标签仅允许 `definition`（定义法）、`substitution`（代入/换元）、`monotonicity`（单调性）、`symmetry`（对称性）、`special_value`（特殊值/中间值）、`intermediate_value`（连续函数零点存在性）、`graph_transform`（图象变换）、`zero_analysis`（零点分析）、`bisection`（二分法）、`function_model`（函数建模）。未在本词表的方法暂不强行误标，待教师确认再版本化扩充。

每题一个主要知识点，表示主要考查目标；可有多个相关知识点、能力与方法标签。相关知识表示解题背景，不自动获得本题正确/错误证据。题级额外前置可按题意指定。参数题必须标 `parameter_analysis`，但不再建立“含参数函数”核心节点。标签由题意与解法确认，不能依据答案错误自动推断能力缺陷。

大型题库拟记录 `source_id`、实际文件路径/页码/原题号、题目版本、教师审核状态；先按来源与原题号识别重复，再核对正文，不能只因题干相同就合并不同选项/答案的题。原始题干、选项、答案、解释不因重新分类而改变。所有映射需可追溯至体系版本和审阅者。

## 难度 1–5 标准

难度是题目认知负荷的教师评定，不按知识点“高级”或含参数自动定为5；预计用时是辅助，不是唯一依据。

| difficulty | 标准 | 示例特征 |
| --- | --- | --- |
| 1 | 单概念识别或直接代入，条件显式 | 判断函数、读取定义域端点 |
| 2 | 熟悉情境的一至两步运用 | 根式与分母限制取交集、单个图象变换 |
| 3 | 多步但常规，整合两类条件或性质 | 区间端点与顶点比较、借助中间值比较 |
| 4 | 参数约束、非直接转化或必要分类，推理链较长 | 顶点位置分类、方程根个数分析 |
| 5 | 多知识综合、多边界分类或较新颖情境，需完整论证 | 参数与分段零点综合、复杂情境模型检验 |

先保留现有 Q001–Q006 的 1、2、2、3、4、5 难度。Q005/Q006 的实际认知负荷可能低于当前标值，后续教师可以单独复评；本次不重评、不修改。历史 D 指标不能因后台改题难度被静默重写，后续需保留题目版本与作答时难度依据。

## 旧知识点迁移对照

旧数据库中的直接前置是：K001 无；K002→K001；K003→K001/K002；K004→K002/K003；K005→K003/K004。上述关系已经只读核对。

| 旧体系 | 新体系映射 | 历史证据处理 |
| --- | --- | --- |
| K001 函数概念 | function_v2:K001 函数概念与三要素 | 按题目保留概念证据，不宣称覆盖新增三要素所有子内容 |
| K002 定义域 | function_v2:K002 定义域、值域与函数表示 | 原定义域题只证明定义域表现，不把新值域/表示能力标为已验证 |
| K003 函数单调性 | function_v2:K003 | 保持主考查目标，相关函数族按题补标 |
| K004 函数最值 | function_v2:K004 | 保持主考查目标，相关函数族按题补标 |
| K005 含参数函数 | 不做节点一对一迁移；逐题归主要知识点，加 parameter_analysis | 绝不能直接改名成新 K005 奇偶性；无法确认的旧题保持待审，不参与 v2 指标 |

### 现有 6 道旧题的重新映射草案

| 题号 / 原知识点 | 新主要知识点 | 相关知识点 | ability_tag | method_tag | 难度 |
| --- | --- | --- | --- | --- | --- |
| Q001 / 旧 K001：判断非函数对应 | K001 | 无 | concept_understanding, logical_reasoning | definition, special_value | 1 |
| Q002 / 旧 K002：根式分式定义域 | K002 | K001 | calculation, logical_reasoning | definition | 2 |
| Q003 / 旧 K003：二次函数递减区间 | K003 | K007 | graph_analysis, logical_reasoning | monotonicity, symmetry | 2 |
| Q004 / 旧 K004：闭区间二次函数最值 | K004 | K007 | calculation, logical_reasoning | substitution, monotonicity, special_value | 3 |
| Q005 / 旧 K005：含参数二次函数递增条件 | K003 | K007 | parameter_analysis, logical_reasoning, graph_analysis | monotonicity, symmetry | 4 |
| Q006 / 旧 K005：含参数二次式恒非负 | K004 | K007 | parameter_analysis, logical_reasoning, calculation | substitution, monotonicity, special_value | 5 |

Q003–Q006 涉及二次函数背景，但不作为 K007 的直接掌握度证据，以免与 K003/K004 双重计数。其题级额外前置拟包括 K007；后续选题查询必须检查这些前置，防止在学生未验证二次函数背景时盲推该类题。同一题的主要知识点仍只保留一个。

旧 `domain_analysis`、`monotonicity_analysis`、`extrema_analysis`、`parameter_extrema` 不再是合法能力标签。不能全局仅改字符串：例如 `parameter_extrema` 要拆为相关知识目标与 `parameter_analysis`，其他标签也逐题审阅。原标签保留在旧版本，不覆盖丢失。

## 可回退的迁移方案（仅设计）

### 1. 版本隔离，避免 ID 语义冲突

不 UPDATE/DELETE 旧 `knowledge_points`；不改 `questions.knowledge_point_id`、题目内容及 `attempts`。拟以新增旁路表承载 v2，旧服务继续读取旧体系。裸 K005 不能跨版本使用；外部/缓存标识必须包含 `(taxonomy_version, knowledge_point_id)`。

后续最小新增结构拟为：

| 拟新增表 | 主要字段与约束 |
| --- | --- |
| taxonomy_versions | version 主键、status（draft/active/retired）、created_at；当前活动版本单独配置且只能有一个 |
| knowledge_catalog | taxonomy_version、id、name、topic、description、display_order；复合主键 (taxonomy_version, id) |
| knowledge_prerequisites | taxonomy_version、knowledge_point_id、prerequisite_id；两端复合外键指向同版本 catalog，复合唯一键、禁止自环；应用校验无环 |
| question_knowledge_mappings | taxonomy_version、question_id、knowledge_point_id、role（primary/related）、review_status；question_id 外键；知识点复合外键；每版本每题最多一个 primary，激活前恰好一个已批准 primary |
| question_tags | taxonomy_version、question_id、tag_type（ability/method）、tag；复合唯一键；词表校验 |
| question_prerequisites | taxonomy_version、question_id、knowledge_point_id；表示题级额外必要基础，复合唯一键及外键 |
| question_sources | source_id、question_id、locator、source_version、review_status；只存核实后的真实位置，来源未到位不能编造页码 |
| taxonomy_migrations | migration_id、source_version、target_version、mapping_digest、status、applied_at；记录审计与幂等性，不记录学生私密信息 |

这些是预期 schema，不在本阶段建表。当前 JSON `prerequisite_ids` 的升级策略：v2 以关系表作为唯一事实来源，数据库层为推荐接口输出有序 ID 列表，必要时生成 JSON 兼容表示；不得双写两个独立图。迁移时验证所有引用、无环、15节点完整以及每题主映射唯一。

### 2. 先在副本演练，再显式切换

1. 原始资料到位并经教师审阅后，冻结 v2 映射清单；先列出未审题与覆盖缺口。
2. 通过 SQLite backup 接口保存包含全部已提交记录的一致副本，记录校验值和各表行数；如有 WAL 不只复制主 db 文件。限制备份访问，备份也不进 Git。
3. 在临时副本演练添加旁路表及映射，使用参数化 SQL、外键和事务；相同 migration_id 与清单摘要重复执行不得新增重复映射，摘要不一致时拒绝静默覆盖。
4. 验证 attempts 全字段/行数/题目引用完全不变，旧题内容、答案、难度与旧图不变；运行完整回归和迁移专用测试。检查每条学习路径是否有满足前置的已审核诊断题，避免仅有依赖后续节点的题形成训练死锁。K007 核心前置已移除 K004，K004↔K007 的隐性循环已解除：可以先在 K001/K002 基础上学习 K007 的入门内容，再做需要 K007 的 K003/K004 旧题。每个开放节点仍须有只依赖核心前置的已审核入门诊断题；不能让它的全部题目都依赖自身或未训练的后继节点。当前6题没有 K007 的主测题，也不覆盖15节点，实际题目可用性尚未满足，不能直接启用 v2。
5. 未来经过用户明确授权才向真实库写入旁路元数据并切换活动版本；切换和审计记录需在事务中完成。此时同步升级查询与服务版本参数，不允许只换标签而继续用旧硬编码查询。
6. 回退首先切回 function_v1，保留 v2 元数据和审计，不删除 attempts。上线后产生的新作答不能因恢复旧备份丢失；完整备份恢复仅在无新记录或完成增量核对的恢复流程中使用。

### 3. 历史作答归属

历史 attempts 不迁移行、不重新评分。通过 question_id 和已批准的 v2 主映射计算新体系视图：Q005 的历史证据归 K003，Q006 归 K004。新 K005 奇偶性从无数据开始，不能继承旧参数题分数。新旧视图并存，不比较没有注明版本的分数。题目正文/答案后来发生变化须创建新题目版本，不能覆写已作答题。

## mastery 兼容方案

当前 `get_function_knowledge_points()` 在数据库层写死 K001–K005；`get_knowledge_attempts()` 按旧题外键 JOIN。因此不能仅新增15节点就声称迁移完成。

后续数据库查询需支持 `taxonomy_version`：获取活动版本的全部函数节点，并经已批准的 `role=primary` 映射 JOIN attempts 与 questions。`calculate_student_mastery` 不再依赖5节点范围；返回全部15节点、体系版本及可追溯覆盖说明。A/R/S/D、等级阈值、证据量规则保持原定义，R/S 仍按 created_at、id 取最近最多5次，不重新评分、不制造作答。

没有直接证据的节点仍为 `mastery_score=None`、`mastery_level=未评估`。相关标签不重复计数；总体训练次数按唯一 attempt_id 汇总。旧 K001/K002 范围扩大时即使得分100%，也只代表已测题表现，画像必须提示尚未覆盖的子内容，证据量不等于知识范围覆盖率。

## recommendation 前置图升级方案

核心 prerequisite 用于知识路径回退，只读取进入节点学习必需的基础；question prerequisite 用于具体题目的可做性判断，不升级成整个节点的统一门槛。数据库层读取本文的 v2 直接前置边，保证排序确定、跨版本引用禁止；继续递归检查 None 或 mastery<0.60 的前置并回退。诊断、补弱、巩固、验证、提升及证据量规则保持不变；提升深度仍由前置图计算，不硬编码 K015。

升级后还需检查题级额外前置：先根据核心图确定可进入的节点，再从其题目中筛选满足题级背景与难度的练习。对主目标节点进行学习时不要求它本身先达到60%；否则未评估节点永远不能开始训练。例如 K003 可训练时，K007 未验证就优先非二次背景题；诊断某节点时不把该节点自身当其题目的额外前置。能力/方法标签用于筛选与解释，不成为掌握度或正式等级。

当前题库只有6题，大多数新节点没有题。未来推荐若遇到无已审题的目标，应明确“该知识点暂缺已审核练习”，可按确定性规则寻找另一个满足前置且有题的目标，并展示原因；不能只为了凑题推高级内容，也不能生成题目补空。此适配仅为后续迁移验收要求，本阶段不修改现有推荐。

## 资料映射与后续验收

`data/source_mapping.json` 是待核实来源登记与映射草案，不是自动导入任务。章节可映射多个知识点，但章节标题映射不能替代逐题 primary/related 判定。原始资料没有提供的节点归入 `unmapped_knowledge_point_ids`，不能暗示已完成题库覆盖。

后续真正迁移前应增加临时数据库测试：旧 K005 不污染新奇偶性；Q005/Q006 分流；15节点均出现；无证据仍未评估；原 attempts 完全保留；映射幂等；前置无环且引用有效；题级前置过滤；无题目标友好处理；体系切换与回退；总体统计不重复；LLM只解释新版本确定性结果。V0.8A 仅校验文件结构/映射图并运行现有全套测试，不执行初始化或迁移。

## 优化后图结构验证

15节点唯一根为 K001，全部非根节点均通过核心前置可达。按已完成核心前置逐轮解锁：K001 → K002 → {K003,K004,K005,K006,K007,K008,K009,K012,K013,K015} → {K010,K014} → K011。花括号表示并行分支，不表示先后必须一致；解锁只是允许进入学习，不代表已掌握。

核心图无环、无自引用；将现有6题的额外 K007 前置纳入结构检查也不会形成循环，因为 K007 只依赖 K001/K002。结构上不存在互相阻塞的必学路径。未来推荐可逐级推进，但实际训练可用性必须另行校验：每个开放节点至少有一条只需要已完成核心前置的入门训练路径，相关专项题可以要求额外知识。现有题库覆盖不完整，因此这里只确认图与设计规则，不宣称15节点已具备实际可训练题目。


## V0.9A 实现状态补充

上述设计现已在隔离副本实现，并未迁移真实数据库。新增8张版本表由 `database/taxonomy_migration.py` 在同一事务中创建，所有知识图从关系表读取。原 questions 的 NOT NULL 外键通过 topic=function_v2、ID=function_v2:Kxxx 的兼容节点承载新题；这些节点不构成第二套前置图，也不进入旧版函数题池。旧5节点、6题及历史 attempts 原行保持不变。版本化查询、mastery、recommendation 和页面使用统一 ACTIVE_TAXONOMY_VERSION 配置，默认仍为 function_v1。

三个批次66道 approved 与旧6道已确认映射题并存：最终覆盖统计只计66道金标准题；副本V2训练池包含72道 approved primary 题。旧Q005→K003、Q006→K004，related K007不计掌握度。未评估保持None。迁移审计固定清单摘要；相同清单幂等，摘要改变拒绝覆盖，出错整笔回滚。真实库路径被本阶段迁移入口拒绝。

隔离启动、配置回退及未来正式切换前置要求见README V0.9A段落。最终覆盖与验收结果分别位于 reports/function_v2_final_coverage_report.md 与 reports/function_v2_dry_run_validation.json。
