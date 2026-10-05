# Batch 002 定向筛选报告

本批仅生成 reviewed 候选，不代表数学审核通过；未批准、未导入数据库。

检查15份DOCX，识别单项选择题块 177 道（不含知识表、判断题、多选题和解答题）。
与 Batch 001 重复或同来源原题号冲突跳过 39 道；新识别 138 道。
最终 reviewed：26；新识别但需人工恢复的 draft：62。

28道定向标注中，1道因与Batch 001同来源原题号冲突跳过，另1道因本批内部同来源原题号冲突跳过。原题号在不同练习组重复时采用保守规则，不宣称其数学内容必然相同。
其余 50 道未入选，不属于本批定向清单。

## 提取状态

| 状态 | 全部扫描 | 新题待审排除 |
|---|---:|---:|
| complete | 112 | 0 |
| formula_warning | 3 | 2 |
| image_required | 33 | 32 |
| incomplete | 12 | 12 |
| manual_review | 17 | 16 |

## 知识点分布

| 知识点 | reviewed |
|---|---:|
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

## 难度分布

| difficulty | 数量 |
|---|---:|
| 1 | 3 |
| 2 | 7 |
| 3 | 10 |
| 4 | 6 |
| 5 | 0 |

## ability_tag

| 标签 | 数量 |
|---|---:|
| calculation | 17 |
| classification_discussion | 2 |
| concept_understanding | 8 |
| graph_analysis | 4 |
| logical_reasoning | 17 |
| parameter_analysis | 7 |

## method_tag

| 标签 | 数量 |
|---|---:|
| bisection | 2 |
| definition | 8 |
| graph_transform | 3 |
| intermediate_value | 2 |
| monotonicity | 6 |
| special_value | 8 |
| substitution | 10 |
| symmetry | 5 |
| zero_analysis | 3 |

## 仍然未满足的定向目标

K007 找到0道可靠基础单选候选，无法达到至少3道目标。§2.5 顶点、对称轴基础内容主要为知识表和判断题；现有完整二次函数单选主要考查值域、单调性或最值，保持其真实 primary。图象缺失的题留在待审文件。
K001、K008 的可靠新增分别少于3道，不转换多选/判断题，也不生成新题。需要补充原始单选资料或人工恢复待审题。

K009 的新识别完整题主要属于 K011 大小比较；唯一入选前的 K009 题因同来源原题号与 Batch 001 冲突而跳过，不把比较题重标为指数函数来补数量。

## 原始来源（只读）

- data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx
- data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx
- data/raw_sources/function/第二章　§2.12　函数模型的应用.docx
- data/raw_sources/function/第二章　§2.1　函数的概念及其表示.docx
- data/raw_sources/function/第二章　§2.2　函数的单调性与最值.docx
- data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx
- data/raw_sources/function/第二章　§2.4　函数的周期性和对称性.docx
- data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx
- data/raw_sources/function/第二章　§2.6　指数与指数函数.docx
- data/raw_sources/function/第二章　§2.7　对数与对数函数.docx
- data/raw_sources/function/第二章　§2.8　指、对、幂的大小比较.docx
- data/raw_sources/function/第二章　§2.9　函数的图象.docx
- data/raw_sources/function/第二章　必刷小题2　函数的概念与性质.docx
- data/raw_sources/function/第二章　必刷小题3　基本初等函数.docx
- data/raw_sources/function/第二章　必刷小题4　函数与方程.docx

## 重复跳过审计

| ID | 依据 | 来源 / locator |
|---|---|---|
| FC-11ee3b6e16d4e37b | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 108–114 |
| FC-49c90b51615e2b77 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 123–129 |
| FC-1cc1980945816604 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 45–49 |
| FC-f573ce2f1bf29118 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 228–234 |
| FC-26cc2c439b5f894e | source_question_number | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 235–250 |
| FC-3c28c0e4c0766052 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 182–188 |
| FC-6d442d3d58a22679 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 209–218 |
| FC-1aadc879a4516adb | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 49–54 |
| FC-51b9b46d2fed57db | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 197–205 |
| FC-39281763772a263b | source_question_number | data/raw_sources/function/第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 237–243 |
| FC-fd25b22d8ec65d5c | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 244–247 |
| FC-562f248c484bec0e | source_question_number | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 21–28 |
| FC-29ef01d7887b3d1f | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 112–120 |
| FC-59ff546df9729f4c | source_question_number | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 131–142 |
| FC-24b2a5d6da66252a | source_question_number | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 192–204 |
| FC-dcbf683dea4dc1fc | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 217–228 |
| FC-08025b5b12538373 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.4　函数的周期性和对称性.docx / word/document.xml paragraphs 26–30 |
| FC-20f50e3124caebc3 | source_question_number | data/raw_sources/function/第二章　§2.4　函数的周期性和对称性.docx / word/document.xml paragraphs 210–221 |
| FC-1fed63316dbc43f0 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 49–55 |
| FC-3ead1c53dde020ab | source_question_number | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 56–63 |
| FC-664306d6909ade55 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 221–227 |
| FC-84abe4b8d9ab891b | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 228–235 |
| FC-2150d246208d0c34 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 44–48 |
| FC-c9b1f87485bf84f5 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 49–52 |
| FC-aa3d672e409dacb6 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 243–247 |
| FC-c339f3342482066b | source_question_number | data/raw_sources/function/第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 248–252 |
| FC-783622fa4ef45e79 | source_question_number | data/raw_sources/function/第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 253–259 |
| FC-9eb44d0e0b702fdb | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 46–50 |
| FC-74b70ecc6132b494 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 188–192 |
| FC-8b574b54c7cec832 | source_question_number | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 193–198 |
| FC-d5bf4280aa1a4a74 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.8　指、对、幂的大小比较.docx / word/document.xml paragraphs 15–23 |
| FC-6fc423432375510b | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　§2.8　指、对、幂的大小比较.docx / word/document.xml paragraphs 119–123 |
| FC-38806b67b3071e71 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 10–14 |
| FC-e530293f6582b191 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 15–19 |
| FC-2b53a97253350c5f | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题3　基本初等函数.docx / word/document.xml paragraphs 4–9 |
| FC-067ebc0866587aed | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 4–9 |
| FC-17f3cef007cde7a3 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 10–17 |
| FC-8e06cbfbfd215db4 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 18–24 |
| FC-ed0b8f423ca3a336 | id, fingerprint, normalized_stem, source_locator, source_question_number | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 33–41 |

## 待审排除明细

| ID | 状态 | 来源 / locator |
|---|---|---|
| FC-ae50847d107d3682 | incomplete | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 19–23 |
| FC-d6aa81e478c7b50e | formula_warning | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 24–45 |
| FC-e6af256f9675b785 | image_required | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 100–106 |
| FC-ff382e5c8180768b | image_required | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 120–128 |
| FC-78b3c0150ab0b23f | image_required | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 131–140 |
| FC-e03ad7a255ae654f | manual_review | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 156–166 |
| FC-47729bb7992a6883 | image_required | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 194–201 |
| FC-f6707a7d443598cf | manual_review | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 202–209 |
| FC-e65ae60151891373 | image_required | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 220–230 |
| FC-29fb3f7e72025f2f | manual_review | data/raw_sources/function/第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 307–315 |
| FC-a13a80086afa2063 | image_required | data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 16–29 |
| FC-f9db2fe930f1976a | image_required | data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 44–57 |
| FC-1d41642be1a56990 | image_required | data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 60–69 |
| FC-5c049d96f1d3e601 | image_required | data/raw_sources/function/第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 86–93 |
| FC-231d1c31cbe808be | image_required | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 50–72 |
| FC-d5dedd5ffa6b638e | image_required | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 97–107 |
| FC-91386458c5c9bcd9 | image_required | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 125–134 |
| FC-ff006b2d1937330b | image_required | data/raw_sources/function/第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 251–258 |
| FC-1fdc5ed17efe36d0 | incomplete | data/raw_sources/function/第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 23–27 |
| FC-4fdb1e6d59574457 | manual_review | data/raw_sources/function/第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 189–193 |
| FC-f4b1b9c06bed7ad3 | incomplete | data/raw_sources/function/第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 203–208 |
| FC-64dc59622df14ac6 | manual_review | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 95–111 |
| FC-f56964918d7aa60a | manual_review | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 144–152 |
| FC-09ee20f11cd4b810 | manual_review | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 170–180 |
| FC-b4dfd7ee7fa3674c | manual_review | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 183–191 |
| FC-8ffa62558c4643ff | manual_review | data/raw_sources/function/第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 237–242 |
| FC-5cba0557edf28c73 | image_required | data/raw_sources/function/第二章　§2.4　函数的周期性和对称性.docx / word/document.xml paragraphs 197–204 |
| FC-506c7bae3d9d4275 | image_required | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 88–94 |
| FC-b4acf8a6435a35df | image_required | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 201–209 |
| FC-937dce6ebaa9c864 | image_required | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 244–256 |
| FC-7eb52e17d28db7a2 | image_required | data/raw_sources/function/第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 336–349 |
| FC-b581d514711041c6 | incomplete | data/raw_sources/function/第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 260–267 |
| FC-dbe5f6a11ef8dfe7 | manual_review | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 51–58 |
| FC-217d1275966058a6 | image_required | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 97–107 |
| FC-50253e8842fbb774 | image_required | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 124–132 |
| FC-f65c690dbf074e0e | manual_review | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 218–227 |
| FC-45d3c57c3809ac75 | image_required | data/raw_sources/function/第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 228–240 |
| FC-83aa6cf7fa010b94 | manual_review | data/raw_sources/function/第二章　§2.8　指、对、幂的大小比较.docx / word/document.xml paragraphs 94–100 |
| FC-a3ab2abd9b3dffa4 | manual_review | data/raw_sources/function/第二章　§2.8　指、对、幂的大小比较.docx / word/document.xml paragraphs 124–131 |
| FC-9fb64153d8927dfc | manual_review | data/raw_sources/function/第二章　§2.8　指、对、幂的大小比较.docx / word/document.xml paragraphs 132–137 |
| FC-62db4759c0826bf5 | incomplete | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 22–27 |
| FC-cf19f3ff0df59565 | incomplete | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 28–36 |
| FC-06ef5cabc10026f0 | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 72–80 |
| FC-99918a7cd871782b | incomplete | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 81–88 |
| FC-1089ecbc75a74aaf | incomplete | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 93–101 |
| FC-fa34384db9586c9d | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 102–112 |
| FC-a326e0856ecb8076 | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 129–141 |
| FC-4e0ad9e240b81508 | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 143–149 |
| FC-650d3ae3561bc261 | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 186–192 |
| FC-f0caaf327ed4ed7d | incomplete | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 193–198 |
| FC-2d60f5f4c5ea13cc | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 199–207 |
| FC-b4a627108cae66b3 | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 208–215 |
| FC-35f7fdb2ee08cc1f | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 216–222 |
| FC-5e574b0135a953f4 | image_required | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 301–308 |
| FC-cfaa82bc23263ef1 | incomplete | data/raw_sources/function/第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 309–318 |
| FC-1050ea505e7a3101 | manual_review | data/raw_sources/function/第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 52–63 |
| FC-3fdf917059897dcf | formula_warning | data/raw_sources/function/第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 64–87 |
| FC-75616c7d999ff291 | incomplete | data/raw_sources/function/第二章　必刷小题3　基本初等函数.docx / word/document.xml paragraphs 26–32 |
| FC-c9ef3e64cf3ada0f | image_required | data/raw_sources/function/第二章　必刷小题3　基本初等函数.docx / word/document.xml paragraphs 56–71 |
| FC-db931555c8177571 | incomplete | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 25–32 |
| FC-e34893b5a20d647d | manual_review | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 42–45 |
| FC-931a2e2d959442e1 | image_required | data/raw_sources/function/第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 58–64 |
