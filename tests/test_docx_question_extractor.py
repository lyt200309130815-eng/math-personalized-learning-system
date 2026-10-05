"""Synthetic DOCX ZIP fixtures exercise XML, math and broken-source handling."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile

from services.source_extractors.docx_question_extractor import extract_questions, read_docx_blocks

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def paragraph(text):
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def source(self, extra="", options=None, answer="C", stem="1.函数 f(x)=2x+1，求 f(2) 的值。"):
        path = Path(self.directory.name) / "中文函数.docx"
        content = paragraph("函数的概念及其表示") + paragraph(stem)
        content += extra
        content += paragraph(options or "A.1 B.3 C.5 D.7")
        content += paragraph("答案 " + answer) + paragraph("解析 代入 x=2，得到 f(2)=5，故选 C。")
        xml = f'<w:document xmlns:w="{W}" xmlns:m="{M}"><w:body>{content}</w:body></w:document>'
        with ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml.encode("utf-8"))
        return path

    def test_chinese_single_choice_and_read_only_source(self):
        path = self.source()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        questions = extract_questions(path)
        self.assertEqual(len(questions), 1)
        question = questions[0]
        self.assertEqual(set(question.options), set("ABCD"))
        self.assertEqual(question.answer, "C")
        self.assertEqual(question.extraction_status, "complete")
        self.assertEqual(question.quality_status, "reviewed")
        self.assertEqual(question.taxonomy_version, "function_v2")
        self.assertEqual(question.source_question_number, "1.")
        self.assertIn("paragraphs", question.source_locator)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_unsupported_equation_warns_without_fake_formula(self):
        path = self.source(extra="<w:p><m:oMath><m:eqArr><m:e><m:r><m:t>x</m:t></m:r></m:e></m:eqArr></m:oMath></w:p>")
        question = extract_questions(path)[0]
        self.assertEqual(question.extraction_status, "formula_warning")
        self.assertIn("[公式待核]", question.stem)
        self.assertEqual(question.quality_status, "draft")

    def test_supported_fraction_and_radical_are_preserved(self):
        extra = '<w:p><m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>x</m:t></m:r></m:den></m:f><m:rad><m:deg/><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad></m:oMath></w:p>'
        question = extract_questions(self.source(extra=extra))[0]
        self.assertIn("(1)/(x)", question.stem)
        self.assertIn("sqrt(x)", question.stem)
        self.assertEqual(question.extraction_status, "complete")

    def test_one_column_braced_cases_preserve_each_condition(self):
        extra = '<w:p><m:oMath><m:d><m:dPr><m:begChr m:val="{"/><m:endChr m:val=""/></m:dPr><m:e><m:m><m:mr><m:e><m:r><m:t>x&gt;0</m:t></m:r></m:e></m:mr><m:mr><m:e><m:r><m:t>x&lt;2</m:t></m:r></m:e></m:mr></m:m></m:e></m:d></m:oMath></w:p>'
        question = extract_questions(self.source(extra=extra))[0]
        self.assertIn('{x>0; x<2}', question.stem)
        self.assertEqual(question.extraction_status, 'complete')

    def test_multi_column_matrix_remains_formula_warning(self):
        extra = '<w:p><m:oMath><m:d><m:dPr><m:begChr m:val="{"/><m:endChr m:val=""/></m:dPr><m:e><m:m><m:mr><m:e><m:r><m:t>x</m:t></m:r></m:e><m:e><m:r><m:t>y</m:t></m:r></m:e></m:mr></m:m></m:e></m:d></m:oMath></w:p>'
        question = extract_questions(self.source(extra=extra))[0]
        self.assertEqual(question.extraction_status, 'formula_warning')
        self.assertIn('[公式待核]', question.stem)

    def test_images_are_not_silently_dropped(self):
        question = extract_questions(self.source(extra="<w:p><w:r><w:drawing/></w:r></w:p>"))[0]
        self.assertEqual(question.extraction_status, "image_required")
        self.assertTrue(question.image_resources)
        self.assertEqual(question.quality_status, "draft")

    def test_missing_option_and_invalid_answer_are_incomplete(self):
        self.assertEqual(extract_questions(self.source(options="A.1 B.3 C.5"))[0].extraction_status, "incomplete")
        self.assertEqual(extract_questions(self.source(answer="E"))[0].extraction_status, "incomplete")

    def test_missing_formula_tail_requires_review(self):
        question = extract_questions(self.source(stem="1.已知函数 f(x)="))[0]
        self.assertEqual(question.extraction_status, "manual_review")

    def test_multiselect_is_not_imported_as_single_choice(self):
        self.assertEqual(extract_questions(self.source(answer="AC")), [])

    def test_superscript_run_fragments_are_merged(self):
        extra = '<w:p><w:r><w:t>x</w:t></w:r><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>2</w:t></w:r><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t>a</w:t></w:r></w:p>'
        blocks = read_docx_blocks(self.source(extra=extra))
        self.assertIn("x^(2a)", "\n".join(block["text"] for block in blocks))

    def test_word_lock_file_is_skipped(self):
        path = Path(self.directory.name) / "~$资料.docx"
        path.write_bytes(b"lock")
        self.assertEqual(extract_questions(path), [])

    def test_missing_all_option_markers_still_creates_incomplete_candidate(self):
        question = extract_questions(self.source(options="选项内容提取失败"))[0]
        self.assertEqual(question.extraction_status, "incomplete")

    def test_fraction_start_does_not_truncate_explanation(self):
        path = self.source()
        with ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        xml = xml.replace("</w:body>", paragraph("(1)/(a)=2，随后计算得到结果。").replace("</w:p>", "</w:p>", 1) + "</w:body>")
        with ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
        self.assertIn("(1)/(a)", extract_questions(path)[0].explanation)
