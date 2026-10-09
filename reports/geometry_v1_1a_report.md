# V1.1A Geometry 扫描与提取报告

共 12 份 DOCX；没有未检测到图片的文件。

| 完整文件名 | embedded media | drawing | pict |
|---|---:|---:|---:|
| 第七章　§7.10　立体几何中的动态、轨迹问题.docx | 29 | 29 | 0 |
| 第七章　§7.1　基本立体图形、简单几何体的表面积与体积.docx | 50 | 50 | 0 |
| 第七章　§7.2　球的切、接问题.docx | 30 | 30 | 0 |
| 第七章　§7.3　空间点、直线、平面之间的位置关系.docx | 53 | 53 | 0 |
| 第七章　§7.4　空间直线、平面的平行.docx | 45 | 45 | 0 |
| 第七章　§7.5　空间直线、平面的垂直.docx | 42 | 42 | 0 |
| 第七章　§7.6　空间向量的概念与运算.docx | 28 | 28 | 0 |
| 第七章　§7.7　向量法求空间角.docx | 41 | 41 | 0 |
| 第七章　§7.8　空间距离及立体几何中的探索性问题.docx | 32 | 32 | 0 |
| 第七章　§7.9　立体几何中的截面、交线问题.docx | 31 | 31 | 0 |
| 第七章　必刷大题14　空间向量与立体几何.docx | 10 | 10 | 0 |
| 第七章　必刷小题13　立体几何.docx | 16 | 16 | 0 |

提取结果：261 条候选题，407 个正文图形实例，38 个未关联图形，0 个 page_render_fallback，0 个 approved。
所有题目和图形均待人工审核；73 条候选题存在公式或结构警告。
未生成页面截图，未导入数据库。

验证命令：
- python -X utf8 scripts/extract_geometry_batch.py
- python -X utf8 -m unittest tests.test_geometry_pipeline tests.test_docx_question_extractor（18 项通过）
- git -c safe.directory=E:/Projects/math_ai diff --check（通过）
