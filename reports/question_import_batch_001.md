# 第一批函数题候选导入报告

## 范围与状态

只读取原 DOCX；每文件最多检查12个选择题候选，不代表全书题目总量。跳过 Word ~$ 临时锁文件；未处理第二批。
complete 表示提取完整性检查通过，不表示答案已由数学求解器证明。知识点、标签、难度为待教师核实草标。
本批可靠候选均为 reviewed，批准数为0；正式批准必须逐题核对原文、答案与解析。原始题号未知时为 null，不编造页码。

已读取 DOCX：15；识别候选：159；完整性通过：84；进入 batch_001：29。

| extraction_status | 数量 |
| --- | --- |
| complete | 84 |
| formula_warning | 22 |
| image_required | 29 |
| incomplete | 13 |
| manual_review | 11 |

最终预检查增加对数分式作用范围检测；84道结构完整候选中筛选29道，另55道完整题未进入本批，不构成第二批。75道有问题的候选保留待审定位。

## batch_001 分布

| 知识点 | 数量 |
| --- | --- |
| K001 | 1 |
| K002 | 3 |
| K003 | 2 |
| K004 | 2 |
| K005 | 2 |
| K006 | 2 |
| K007 | 0 |
| K008 | 1 |
| K009 | 2 |
| K010 | 2 |
| K011 | 3 |
| K012 | 2 |
| K013 | 2 |
| K014 | 2 |
| K015 | 3 |

| difficulty | 数量 |
| --- | --- |
| 1 | 1 |
| 2 | 18 |
| 3 | 9 |
| 4 | 1 |
| 5 | 0 |

## 原始资料

- 第二章　§2.10　函数的零点与方程的解.docx
- 第二章　§2.11　函数与方程的综合应用.docx
- 第二章　§2.12　函数模型的应用.docx
- 第二章　§2.1　函数的概念及其表示.docx
- 第二章　§2.2　函数的单调性与最值.docx
- 第二章　§2.3　函数的奇偶性.docx
- 第二章　§2.4　函数的周期性和对称性.docx
- 第二章　§2.5　二次函数与幂函数.docx
- 第二章　§2.6　指数与指数函数.docx
- 第二章　§2.7　对数与对数函数.docx
- 第二章　§2.8　指、对、幂的大小比较.docx
- 第二章　§2.9　函数的图象.docx
- 第二章　必刷小题2　函数的概念与性质.docx
- 第二章　必刷小题3　基本初等函数.docx
- 第二章　必刷小题4　函数与方程.docx

## 未进入可靠批次的题目

详情保存在 `data/question_bank/review_required/function_batch_001.jsonl`；图片只记录内部资源引用，不伪造图象。

| 候选ID | 来源及定位 | 状态 | 原因 |
| --- | --- | --- | --- |
| FC-ae50847d107d3682 | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 19–23 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-d6aa81e478c7b50e | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 24–45 | formula_warning | 提取状态非 complete; 表格结构需人工核对 |
| FC-e6af256f9675b785 | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 100–106 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-6de879090475aa65 | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 111–119 | formula_warning | stem 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-ff382e5c8180768b | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 120–128 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-78b3c0150ab0b23f | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 131–140 | image_required | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-e03ad7a255ae654f | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 156–166 | manual_review | 涉及未标注的三角函数基础，需人工确认可做性 |
| FC-47729bb7992a6883 | 第二章　§2.10　函数的零点与方程的解.docx / word/document.xml paragraphs 194–201 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-a13a80086afa2063 | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 16–29 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-0478c62e1b045942 | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 35–43 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-f9db2fe930f1976a | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 44–57 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-1d41642be1a56990 | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 60–69 | image_required | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-5c049d96f1d3e601 | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 86–93 | image_required | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-846d281fa416d49e | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 115–122 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-4e5e69b569c6fa0d | 第二章　§2.11　函数与方程的综合应用.docx / word/document.xml paragraphs 130–139 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-231d1c31cbe808be | 第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 50–72 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 表格结构需人工核对 |
| FC-d5dedd5ffa6b638e | 第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 97–107 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-91386458c5c9bcd9 | 第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 125–134 | image_required | stem 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-26cc2c439b5f894e | 第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 235–250 | formula_warning | 提取状态非 complete; 表格结构需人工核对 |
| FC-ff006b2d1937330b | 第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 251–258 | image_required | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-7ba9f92bc1f1fd47 | 第二章　§2.12　函数模型的应用.docx / word/document.xml paragraphs 259–267 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-1fdc5ed17efe36d0 | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 23–27 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-b4700be0ae9bf7e9 | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 60–66 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-f0a581932fb45f1e | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 154–165 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-4fdb1e6d59574457 | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 189–193 | incomplete | 主要知识点无效; stem 数学表达式可能残缺; 涉及未标注的三角函数基础，需人工确认可做性; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-f4b1b9c06bed7ad3 | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 203–208 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-10fd3ba793bf472e | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 219–227 | incomplete | 主要知识点无效 |
| FC-265703367fd00145 | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 228–236 | formula_warning | stem 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-0f2d7c528d11c579 | 第二章　§2.1　函数的概念及其表示.docx / word/document.xml paragraphs 237–248 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-d94de56135f10760 | 第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 41–48 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-5dadbfa7bb14b299 | 第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 186–193 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-39281763772a263b | 第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 237–243 | image_required | explanation 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-b08ee5243be1be77 | 第二章　§2.2　函数的单调性与最值.docx / word/document.xml paragraphs 248–253 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-562f248c484bec0e | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 21–28 | manual_review | 涉及未标注的三角函数基础，需人工确认可做性 |
| FC-64dc59622df14ac6 | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 95–111 | manual_review | 涉及未标注的三角函数基础，需人工确认可做性 |
| FC-f56964918d7aa60a | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 144–152 | manual_review | explanation 上下标嵌套或主体缺失，需核对公式 |
| FC-9fc41fce2cc843d9 | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 192–208 | image_required | explanation 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-8ffa62558c4643ff | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 237–242 | manual_review | 涉及未标注的三角函数基础，需人工确认可做性 |
| FC-5cba0557edf28c73 | 第二章　§2.4　函数的周期性和对称性.docx / word/document.xml paragraphs 197–204 | image_required | explanation 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-506c7bae3d9d4275 | 第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 88–94 | image_required | stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-d778c4634db1d038 | 第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 201–213 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-345e2f7aadb1676d | 第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 236–243 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-937dce6ebaa9c864 | 第二章　§2.5　二次函数与幂函数.docx / word/document.xml paragraphs 244–256 | image_required | stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-c339f3342482066b | 第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 248–252 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-b581d514711041c6 | 第二章　§2.6　指数与指数函数.docx / word/document.xml paragraphs 260–267 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-dbe5f6a11ef8dfe7 | 第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 51–58 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-217d1275966058a6 | 第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 97–107 | image_required | explanation 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-50253e8842fbb774 | 第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 124–132 | image_required | stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-8b574b54c7cec832 | 第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 193–198 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-05a6b59ac68ffe8f | 第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 228–241 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-62db4759c0826bf5 | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 22–27 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-cf19f3ff0df59565 | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 28–36 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-06ef5cabc10026f0 | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 72–80 | image_required | stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-99918a7cd871782b | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 81–88 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-1089ecbc75a74aaf | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 93–101 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 涉及未标注的三角函数基础，需人工确认可做性; 包含未确认的图片资源; 提取状态非 complete |
| FC-fa34384db9586c9d | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 102–112 | image_required | stem 数学表达式可能残缺; 涉及未标注的三角函数基础，需人工确认可做性; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-a326e0856ecb8076 | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 129–141 | image_required | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-4e0ad9e240b81508 | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 143–149 | image_required | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-650d3ae3561bc261 | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 186–192 | image_required | stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-f0caaf327ed4ed7d | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 193–198 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-2d60f5f4c5ea13cc | 第二章　§2.9　函数的图象.docx / word/document.xml paragraphs 199–207 | image_required | stem 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |
| FC-5672161c8b5753c9 | 第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 4–9 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-3fdf917059897dcf | 第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 64–87 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-75616c7d999ff291 | 第二章　必刷小题3　基本初等函数.docx / word/document.xml paragraphs 26–32 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 包含未确认的图片资源; 提取状态非 complete |
| FC-b3b1037f1d4da287 | 第二章　必刷小题3　基本初等函数.docx / word/document.xml paragraphs 33–41 | formula_warning | explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-ef6c338f0ea9d9f9 | 第二章　必刷小题3　基本初等函数.docx / word/document.xml paragraphs 56–72 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-db931555c8177571 | 第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 25–32 | incomplete | A/B/C/D 选项缺失或为空; stem 数学表达式可能残缺; 涉及未标注的三角函数基础，需人工确认可做性; 包含未确认的图片资源; 提取状态非 complete |
| FC-fb4c726e650a7c88 | 第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 46–57 | formula_warning | stem 数学表达式可能残缺; explanation 数学表达式可能残缺; 提取状态非 complete; 包含无法可靠转换的 OMML 公式 |
| FC-659078ff663db0d9 | 第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 58–65 | image_required | explanation 数学表达式可能残缺; 图象依赖尚未人工确认，需图片审核; 包含未确认的图片资源; 提取状态非 complete |

| FC-e34893b5a20d647d | 第二章　必刷小题4　函数与方程.docx / word/document.xml paragraphs 42–45 | manual_review | stem 对数与分式的作用范围不明确，需核对原公式; explanation 对数与分式的作用范围不明确，需核对原公式 |

| FC-09ee20f11cd4b810 | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 170–180 | manual_review | stem 对数与分式的作用范围不明确，需核对原公式; explanation 对数与分式的作用范围不明确，需核对原公式 |

| FC-b4dfd7ee7fa3674c | 第二章　§2.3　函数的奇偶性.docx / word/document.xml paragraphs 183–191 | manual_review | stem 对数与分式的作用范围不明确，需核对原公式; explanation 对数与分式的作用范围不明确，需核对原公式 |

| FC-f65c690dbf074e0e | 第二章　§2.7　对数与对数函数.docx / word/document.xml paragraphs 218–227 | manual_review | explanation 对数与分式的作用范围不明确，需核对原公式 |

| FC-83aa6cf7fa010b94 | 第二章　§2.8　指、对、幂的大小比较.docx / word/document.xml paragraphs 94–100 | manual_review | stem 对数与分式的作用范围不明确，需核对原公式; explanation 对数与分式的作用范围不明确，需核对原公式 |

| FC-1050ea505e7a3101 | 第二章　必刷小题2　函数的概念与性质.docx / word/document.xml paragraphs 52–63 | manual_review | stem 对数与分式的作用范围不明确，需核对原公式; explanation 对数与分式的作用范围不明确，需核对原公式 |

## 导入与兼容边界

本次没有批准或导入真实题目。approved-only 导入器在显式指定的隔离库中维护 function_v2 题库表，禁止真实 math_ai.db。
旧训练、mastery、recommendation、feedback 继续使用旧 questions，不读取候选题，也不把新 K005 奇偶性解释为旧参数题。
v2 审批题库提供 approved-only 查询边界；正式接入页面与推荐、启用15节点需另行完成 V0.8A 迁移验收，不在此批次自动切换。

## 验证结果

全部126项离线自动测试通过（原有94项、新增32项），导入验收仅使用临时 SQLite 数据库。真实 math_ai.db 与15份原始 DOCX 的 SHA-256 保持一致，未修改任何真实 attempts；未调用 LLM，未批准或导入本批候选。
