"""Synthetic packages verify extraction provenance and strict draft staging."""
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from services.source_extractors.geometry_pipeline import build_pipeline


class GeometryPipelineTests(unittest.TestCase):
    def run_fixture(self, target='media/image1.png', external=False, media=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / 'source'
        source.mkdir()
        path = source / '资料.DOCX'
        drawing = '<w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>'
        content = drawing + '<w:p><w:r><w:t>例1 如图求体积</w:t></w:r></w:p>' + drawing
        content += '<w:p><w:r><w:t>解析 方法说明</w:t></w:r></w:p>' + drawing
        content += '<w:p><w:r><w:t>思维升华 总结</w:t></w:r></w:p>' + drawing
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
               'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
               '<w:body>' + content + '</w:body></w:document>')
        with ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
            mode = ' TargetMode="External"' if external else ''
            archive.writestr('word/_rels/document.xml.rels',
                             f'<Relationships><Relationship Id="rId1" Target="{target}"{mode}/></Relationships>')
            if media:
                archive.writestr('word/media/image1.png', b'original image bytes')
        original = path.read_bytes()
        output = root / 'output'
        result = build_pipeline(source, output)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(result['database_imported'])
        self.assertEqual(result['approved_count'], 0)
        return result, output, source

    def test_original_bytes_roles_and_repeatability(self):
        import json
        result, output, source = self.run_fixture()
        self.assertEqual(result['asset_count'], 4)
        self.assertEqual(result['unassigned_asset_count'], 2)
        rows = [json.loads(line) for line in (output / 'diagram_assets.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['role'] for r in rows], ['unassigned', 'stem', 'explanation', 'unassigned'])
        for row in rows:
            self.assertEqual(row['review_status'], 'pending_review')
            self.assertEqual((output / row['resources'][0]['path']).read_bytes(), b'original image bytes')
        first = (output / 'questions.jsonl').read_bytes()
        build_pipeline(source, output)
        self.assertEqual(first, (output / 'questions.jsonl').read_bytes())

    def test_missing_media_requires_fallback(self):
        result, _, _ = self.run_fixture(media=False)
        self.assertEqual(result['fallback_count'], 4)

    def test_external_media_never_downloaded(self):
        result, _, _ = self.run_fixture(target='https://example.invalid/diagram.png', external=True)
        self.assertEqual(result['fallback_count'], 4)

    def test_non_media_target_requires_fallback(self):
        result, _, _ = self.run_fixture(target='../document.xml')
        self.assertEqual(result['fallback_count'], 4)

    def test_source_directory_output_rejected(self):
        _, _, source = self.run_fixture()
        with self.assertRaises(ValueError):
            build_pipeline(source, source / 'generated')
