# V1.1A 立体几何候选题与图形资产流水线

运行 `python scripts/extract_geometry_batch.py`，默认读取 `data/raw_sources/geometry` 下全部 DOCX（递归、不区分扩展名大小写、跳过 Word 锁文件）。输出到 `data/question_bank/geometry_v1_1a`，不连接或修改数据库。

- `scan_report.json`：完整文件名、来源哈希、包内 media 数和 drawing/pict/object 节点数。节点数包括页眉页脚等 Word XML 部件，不能直接视为题目配图数。
- `questions.jsonl`：几何候选题，保留题干、答案、解析、公式警告和 XML 段落范围。编号题与例题构成草稿边界；不推断正式知识点、评分细则或正确答案。
- `diagram_assets.jsonl`：正文中的图形实例、源关系、原始媒体哈希、题目关联及用途。保留原始媒体字节及 `drawing.xml`，不截取整页 Word 页面。
- `review_queue.jsonl`：全部候选题和图形进入人工审核。引言和总结中的图形可保持未关联；解析图不能自动充当题干图。

全部记录均为 `draft` / `pending_review`。媒体缺失、外链、非独立媒体及无法提取的 Word 图形标记 `page_render_fallback`，不自动渲染、不自动批准。此标记只代表需要人工处理，绝不代表已有合格题图。EMF/WMF 等原始格式保留，尚未转换成浏览器预览格式。

审核时应核对题目边界、图文对应、题干图与解析图、公式完整性、图片是否为页面或装饰、知识点、答案与来源许可。段落位置不是页码；文本框、表格、重复题号和复杂公式仍可能需要人工修正。当前不提供正式入库或批准动作。
