"""Geometry V1.1B: offline human review documents and verifiable draft metadata.

No approval inference, formula repair, reassociation or production writes.
DOCX is generated directly with standard-library OOXML and Pillow image decoding.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image

from services.question_deduplication import normalize_stem
from services.question_validator import content_fingerprint
from services.source_extractors.docx_question_extractor import W, M, read_docx_blocks

ROOT = Path(__file__).resolve().parents[1]
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
PIC = '{http://schemas.openxmlformats.org/drawingml/2006/picture}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
for prefix, uri in [('w', W), ('m', M), ('r', R), ('wp', WP), ('a', A), ('pic', PIC)]:
    ET.register_namespace(prefix, uri[1:-1])

KNOWLEDGE = dict(zip([f'G{i:03}' for i in range(1, 11)], [
    '基本立体图形与表面积体积', '球的切接问题', '空间点线面位置关系',
    '空间直线、平面的平行', '空间直线、平面的垂直', '空间向量概念与运算',
    '向量法求空间角', '空间距离', '截面与交线问题', '动态与轨迹问题']))
CHECKS = ['题目边界正确', '公式完整', '图像正确', '答案正确', '解析完整', '知识点合理', '可批准', '拒绝']


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def database_snapshot(path):
    """Hash DB and sidecars without opening a write connection."""
    return {str(p): file_hash(p) for p in [path, Path(str(path) + '-wal'), Path(str(path) + '-shm'),
                                          Path(str(path) + '-journal')] if p.exists()}


def image_check(resource, staging):
    path = (staging / resource['path']).resolve()
    if staging.resolve() not in path.parents:
        return {'legal': False, 'warnings': ['图片路径越界']}
    try:
        if file_hash(path) != resource['sha256']:
            return {'legal': False, 'warnings': ['原始媒体哈希不匹配']}
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            # Display at 150 dpi, capped at 6 inches; never upscale tiny images.
            warnings = ['IMAGE QUALITY WARNING'] if min(width, height) < 100 or max(width, height) < 240 else []
            return {'legal': True, 'width': width, 'height': height, 'format': image.format,
                    'display_width_inches': min(width / 150, 6, height and 8 * width / height),
                    'warnings': warnings}
    except (OSError, ValueError) as error:
        return {'legal': False, 'warnings': [f'图片解码失败：{error}']}


def paragraph_number(asset):
    match = re.search(r'paragraph (\d+) visual (\d+)', asset['source_locator'])
    return tuple(map(int, match.groups())) if match else (0, 0)


def classify_assets(questions, assets, staging, blocks):
    """Verify position and membership; role inference remains explicitly provisional."""
    by_id = {q['id']: q for q in questions}
    memberships = defaultdict(list)
    for question in questions:
        for asset_id in question['asset_ids']:
            memberships[asset_id].append(question['id'])
    results = []
    source_media = {}
    for filename in blocks:
        # Read package media, never a rendered Word page.
        with ZipFile(filename) as archive:
            source_media[filename] = {name: hashlib.sha256(archive.read(name)).hexdigest()
                                      for name in archive.namelist() if name.startswith('word/media/') and not name.endswith('/')}
    for source in assets:
        row = deepcopy(source)
        paragraph, _ = paragraph_number(row)
        source_blocks = blocks[row['source_file']]
        nearby = source_blocks[max(0, paragraph - 3):paragraph + 2]
        row['context_before'] = '\n'.join(b['text'] for b in nearby if b['index'] < paragraph)
        row['context_at'] = next((b['text'] for b in nearby if b['index'] == paragraph), '')
        row['context_after'] = '\n'.join(b['text'] for b in nearby if b['index'] > paragraph)
        row['image_checks'] = [image_check(r, staging) for r in row['resources']]
        question = by_id.get(row['question_id'])
        valid_position = bool(question and question['source_file'] == row['source_file']
                              and question['start_paragraph'] <= paragraph <= question['end_paragraph'])
        table = any('表格' in warning for b in nearby if b['index'] == paragraph for warning in b['warnings'])
        row['verification'] = {'within_question_range': valid_position,
                               'membership_matches': memberships[row['id']] == [row['question_id']] if question else not memberships[row['id']],
                               'multiple_question_bindings': len(memberships[row['id']]) > 1,
                               'table_context': table,
                               'source_verified': file_hash(Path(row['source_file'])) == row['source_sha256'],
                               'media_matches_source': all(source_media[row['source_file']].get(r['package_part']) == r['sha256']
                                                           for r in row['resources'])}
        role = 'unknown'
        if valid_position and not table:
            if source['role'] == 'explanation':
                role = 'solution_diagram'
            elif source['role'] == 'stem':
                # Only an explicit option label in the same paragraph supports option_image.
                role = 'option_image' if re.match(r'^\s*[ABCD][.．、]', row['context_at']) else 'question_diagram'
        row['asset_role'] = role
        row['asset_role_status'] = 'suggested_pending_review'
        row['image_link_confidence'] = ('unlinked' if not question else 'low' if
                                       not valid_position or table or not row['verification']['membership_matches']
                                       or not row['verification']['source_verified'] or not row['verification']['media_matches_source']
                                       else 'medium')
        row['student_render_eligible_role'] = role in {'question_diagram', 'option_image'}
        row['student_render_enabled'] = False
        row['human_action'] = 'pending'
        results.append(row)
    # Report identical media reused across questions; do not assume reuse is a mistake.
    hashes = defaultdict(set)
    for row in results:
        for resource in row['resources']:
            if row['question_id']:
                hashes[resource['sha256']].add(row['question_id'])
    for row in results:
        row['shared_media_question_ids'] = sorted({qid for resource in row['resources']
                                                   for qid in hashes[resource['sha256']]})
    return results


def knowledge_suggestion(stem):
    """Rank actual task wording; chapter title is deliberately not an input."""
    tasks = re.findall(r'(?:求|证明|判断|计算|确定|则|的)([^。；\n]{0,100})', stem)
    objective = '\n'.join(tasks) or stem
    patterns = [('G010', r'轨迹|动点|运动|动态'), ('G009', r'截面|交线|截得|截出'),
                ('G008', r'距离|点到|线到|面到'), ('G007', r'所成角|夹角|二面角|空间角|余弦值|正弦值'),
                ('G002', r'内切球|外接球|切球|接球|球.*半径|球心|球面'),
                ('G001', r'体积|表面积|侧面积|直观图|展开图|结构特征'),
                ('G005', r'垂直|⊥'), ('G004', r'平行|∥'),
                ('G006', r'向量|数量积|坐标|共线|共面'), ('G003', r'位置关系|异面|相交|直线|平面')]
    hits = [key for key, pattern in patterns if re.search(pattern, objective)]
    # A default is a visibly low-confidence draft, never a taxonomy assignment.
    return {'primary': hits[0] if hits else 'G003', 'related': hits[1:],
            'status': 'suggested_pending_review', 'confidence': 'medium' if hits else 'low',
            'basis': objective[:250] if hits else '无充分目标关键词，G003 仅为待修改占位建议'}


def batch_number(filename):
    match = re.search(r'§7\.(\d+)(?!\d)', filename)
    return (int(match[1]) + 1) // 2 if match else 6


def prepare_questions(questions, assets, blocks):
    grouped = defaultdict(list)
    for asset in assets:
        if asset['question_id']:
            grouped[asset['question_id']].append(asset)
    results = []
    for source in questions:
        row = deepcopy(source)
        warnings = []
        row['source_section'] = Path(row['source_file']).stem
        row['batch'] = batch_number(row['source_section'])
        row['raw_candidate'] = {key: row[key] for key in ['stem', 'answer', 'explanation']}
        stem = row['stem'].strip()
        matches = list(re.finditer(r'(?<![A-Za-z])([ABCD])[.．、]\s*', stem))
        options = {}
        if matches:
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(stem)
                if match[1] in options:
                    warnings.append({'warning_type': 'structure_warning', 'warning_field': 'options', 'detail': '重复选项标签'})
                options[match[1]] = stem[match.end():end].strip()
            stem = stem[:matches[0].start()].strip()
        row['stem'] = stem
        row['options'] = options or None
        raw_answer = re.sub(r'^答案\s*[:：]?\s*', '', row['answer'].strip())
        if options:
            letters = re.fullmatch(r'[ABCD](?:[\s、,，]*[ABCD])*', raw_answer)
            row['question_type'] = 'multiple_choice' if ('多选' in stem or letters and len(re.findall('[ABCD]', raw_answer)) > 1) else 'single_choice'
            row['answer'] = raw_answer
            if set(options) != set('ABCD') or any(not x for x in options.values()):
                warnings.append({'warning_type': 'structure_warning', 'warning_field': 'options', 'detail': 'A/B/C/D选项缺失或为空'})
            if not letters:
                warnings.append({'warning_type': 'answer_warning', 'warning_field': 'answer', 'detail': '选择题答案非独立有效选项'})
        elif re.search(r'_{3,}|\u3000{2,}|填空', stem):
            row['question_type'] = 'fill_blank'
            row['answer'] = raw_answer
        else:
            row['question_type'] = 'subjective'
            row['answer'] = raw_answer or row['explanation'].strip()
            if not raw_answer and row['answer']:
                row['answer_provenance'] = '原DOCX解/证明/解析段落，未推算答案'
        row['reference_solution'] = row['explanation']
        row['type_status'] = 'suggested_pending_review'
        if not row['answer'].strip():
            warnings.append({'warning_type': 'answer_warning', 'warning_field': 'answer', 'detail': '答案或reference solution缺失'})
        if not stem or not row['answer'].strip() and not re.search(r'求|证明|判断|选择|计算|填|若|已知', stem):
            warnings.append({'warning_type': 'structure_warning', 'warning_field': 'stem', 'detail': '疑似知识总结或非题目段落；边界需核对'})
        if not row['explanation'].strip():
            warnings.append({'warning_type': 'solution_warning', 'warning_field': 'explanation', 'detail': '解析缺失，需核对原文'})
        source_blocks = blocks[row['source_file']]
        field = 'stem'
        paragraph_fields = {}
        for block in source_blocks:
            if row['start_paragraph'] <= block['index'] <= row['end_paragraph']:
                if re.match(r'^答案', block['text']):
                    field = 'answer'
                elif re.match(r'^(?:解析|解|证明)(?:\s|[:：])', block['text']):
                    field = 'explanation'
                paragraph_fields[block['index']] = field
                for warning in block['warnings']:
                    warnings.append({'warning_type': 'formula_warning' if 'OMML' in warning or '公式' in warning else 'structure_warning',
                                     'warning_field': field, 'paragraph': block['index'], 'detail': warning,
                                     'normalized_text': block['text'], 'requires_source_check': True})
        row['paragraph_fields'] = paragraph_fields
        images = sorted(grouped[row['id']], key=paragraph_number)
        row['review_asset_ids'] = [a['id'] for a in images]
        row['diagram_required'] = bool(re.search(r'如图|下图|图中|图示|图所示', stem))
        valid_stem_diagrams = [a for a in images if a['asset_role'] in {'question_diagram', 'option_image'}
                               and a['verification']['source_verified'] and a['verification']['media_matches_source']
                               and any(c['legal'] for c in a['image_checks'])]
        row['missing_required_diagram'] = row['diagram_required'] and not valid_stem_diagrams
        if row['missing_required_diagram']:
            warnings.append({'warning_type': 'image_warning', 'warning_field': 'stem', 'detail': 'MISSING REQUIRED DIAGRAM'})
        row['image_link_confidence'] = 'low' if any(a['image_link_confidence'] == 'low' for a in images) or row['missing_required_diagram'] else 'medium' if images else 'not_applicable'
        if row['image_link_confidence'] == 'low':
            warnings.append({'warning_type': 'image_link_warning', 'warning_field': 'assets', 'detail': 'image_link_confidence low'})
        for asset in images:
            if not asset['verification']['source_verified'] or not asset['verification']['media_matches_source']:
                warnings.append({'warning_type': 'image_source_warning', 'warning_field': 'assets', 'asset_id': asset['id'],
                                 'detail': '来源DOCX或媒体哈希不匹配，requires_source_check'})
            for check in asset['image_checks']:
                for warning in check['warnings']:
                    warnings.append({'warning_type': 'image_quality_warning', 'warning_field': 'assets', 'asset_id': asset['id'], 'detail': warning})
            if asset['shared_media_question_ids'] and len(asset['shared_media_question_ids']) > 1:
                warnings.append({'warning_type': 'image_reuse_warning', 'warning_field': 'assets', 'asset_id': asset['id'],
                                 'detail': '同媒体跨题复用，仅报告，不认定错误'})
        # Compare all visual positions against staged asset locators to catch omitted second images.
        expected = sum(len(re.findall(r'\[图片待核\]', b['text'])) for b in source_blocks
                       if row['start_paragraph'] <= b['index'] <= row['end_paragraph'])
        row['visual_count_check'] = {'source_visual_placeholders': expected, 'associated_instances': len(images),
                                    'matches': expected == len(images)}
        if expected != len(images):
            warnings.append({'warning_type': 'image_link_warning', 'warning_field': 'assets', 'detail': '源图形数与关联实例数不一致'})
        row['formula_status'] = 'requires_source_check' if any(w['warning_type'] == 'formula_warning' for w in warnings) else 'no_detected_warning'
        row['structure_status'] = 'requires_source_check' if any(w['warning_type'] == 'structure_warning' for w in warnings) else 'no_detected_warning'
        row['knowledge_suggestion'] = knowledge_suggestion(stem)
        if row['knowledge_suggestion']['confidence'] == 'low':
            warnings.append({'warning_type': 'knowledge_warning', 'warning_field': 'primary', 'detail': '知识点证据不足，需人工指定primary'})
        row['difficulty'] = {'suggested': 3 if row['question_type'] == 'subjective' else 2, 'status': 'pending_review',
                             'basis': '题型粗分的人工审核占位值，不是已评定难度'}
        row['warnings'] = warnings
        row['review_group'] = 'warning_candidates' if warnings else 'clean_candidates'
        row['approval_suggestion'] = 'none'
        row['decision'] = 'pending'
        row['fingerprint'] = content_fingerprint(row)
        results.append(row)
    return results


class ReviewDocx:
    """Small OOXML writer embedding native math and actual PNG image parts."""
    def __init__(self, title):
        self.root = ET.Element(W + 'document')
        self.body = ET.SubElement(self.root, W + 'body')
        self.media = []
        self.text(title, bold=True)
        self.text('人工审核资料：全部 pending；题型、知识点、图像角色和难度为待确认建议。无自动批准。')

    def text(self, value, bold=False, warning=False):
        for line in str(value).split('\n'):
            paragraph = ET.SubElement(self.body, W + 'p')
            run = ET.SubElement(paragraph, W + 'r')
            props = ET.SubElement(run, W + 'rPr')
            ET.SubElement(props, W + 'rFonts', {W + 'ascii': 'Calibri', W + 'eastAsia': '宋体'})
            ET.SubElement(props, W + 'sz', {W + 'val': '22'})
            if bold:
                ET.SubElement(props, W + 'b')
            if warning:
                ET.SubElement(props, W + 'color', {W + 'val': 'C00000'})
            ET.SubElement(run, W + 't', {'{http://www.w3.org/XML/1998/namespace}space': 'preserve'}).text = line

    def page_break(self):
        ET.SubElement(ET.SubElement(ET.SubElement(self.body, W + 'p'), W + 'r'), W + 'br', {W + 'type': 'page'})

    def native_source(self, paragraph, *, preserve_scripts=False):
        """Copy paragraph math exactly; remove unrelated drawings/relations."""
        node = deepcopy(paragraph)
        for parent in node.iter():
            for child in list(parent):
                keep_script = (preserve_scripts and child.tag == W + 'rPr'
                               and child.find(W + 'vertAlign') is not None)
                if child.tag in {W + 'drawing', W + 'pict', W + 'object', W + 'pPr', W + 'rPr'} and not keep_script:
                    parent.remove(child)
            for key in list(parent.attrib):
                if key.startswith(R):
                    del parent.attrib[key]
        self.body.append(node)

    def picture(self, path, label, check):
        self.text(label, bold=True)
        if not check['legal']:
            self.text('MISSING REQUIRED DIAGRAM：' + '; '.join(check['warnings']), warning=True)
            return
        if check['warnings']:
            self.text('; '.join(check['warnings']), warning=True)
        with Image.open(path) as source:
            buffer = io.BytesIO()
            source.convert('RGBA').save(buffer, format='PNG')
            width, height = source.size
        self.media.append(buffer.getvalue())
        number = len(self.media)
        cx = round(check['display_width_inches'] * 914400)
        cy = round(cx * height / width)
        p = ET.SubElement(self.body, W + 'p')
        drawing = ET.SubElement(ET.SubElement(p, W + 'r'), W + 'drawing')
        inline = ET.SubElement(drawing, WP + 'inline', dict(distT='0', distB='0', distL='0', distR='0'))
        ET.SubElement(inline, WP + 'extent', dict(cx=str(cx), cy=str(cy)))
        ET.SubElement(inline, WP + 'docPr', dict(id=str(number), name=label, descr=label))
        frame = ET.SubElement(inline, WP + 'cNvGraphicFramePr')
        ET.SubElement(frame, A + 'graphicFrameLocks', dict(noChangeAspect='1'))
        graphic = ET.SubElement(inline, A + 'graphic')
        data = ET.SubElement(graphic, A + 'graphicData', dict(uri=PIC[1:-1]))
        picture = ET.SubElement(data, PIC + 'pic')
        props = ET.SubElement(picture, PIC + 'nvPicPr')
        ET.SubElement(props, PIC + 'cNvPr', dict(id=str(number), name=f'image{number}.png'))
        ET.SubElement(props, PIC + 'cNvPicPr')
        fill = ET.SubElement(picture, PIC + 'blipFill')
        ET.SubElement(fill, A + 'blip', {R + 'embed': f'rId{number}'})
        ET.SubElement(ET.SubElement(fill, A + 'stretch'), A + 'fillRect')
        shape = ET.SubElement(picture, PIC + 'spPr')
        transform = ET.SubElement(shape, A + 'xfrm')
        ET.SubElement(transform, A + 'off', dict(x='0', y='0'))
        ET.SubElement(transform, A + 'ext', dict(cx=str(cx), cy=str(cy)))
        ET.SubElement(ET.SubElement(shape, A + 'prstGeom', dict(prst='rect')), A + 'avLst')

    def save(self, path):
        section = ET.SubElement(self.body, W + 'sectPr')
        ET.SubElement(section, W + 'pgSz', {W + 'w': '11906', W + 'h': '16838'})
        ET.SubElement(section, W + 'pgMar', {W + 'top': '1134', W + 'bottom': '1134', W + 'left': '1134', W + 'right': '1134'})
        types = ET.Element(CT + 'Types')
        for extension, mime in [('rels', 'application/vnd.openxmlformats-package.relationships+xml'), ('xml', 'application/xml'), ('png', 'image/png')]:
            ET.SubElement(types, CT + 'Default', dict(Extension=extension, ContentType=mime))
        ET.SubElement(types, CT + 'Override', dict(PartName='/word/document.xml', ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'))
        package_rels = ET.Element(REL + 'Relationships')
        ET.SubElement(package_rels, REL + 'Relationship', dict(Id='rId1', Type=R[1:-1] + '/officeDocument', Target='word/document.xml'))
        document_rels = ET.Element(REL + 'Relationships')
        for number in range(1, len(self.media) + 1):
            ET.SubElement(document_rels, REL + 'Relationship', dict(Id=f'rId{number}', Type=R[1:-1] + '/image', Target=f'media/image{number}.png'))
        path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
            for name, node in [('[Content_Types].xml', types), ('_rels/.rels', package_rels),
                               ('word/document.xml', self.root), ('word/_rels/document.xml.rels', document_rels)]:
                archive.writestr(name, ET.tostring(node, encoding='utf-8', xml_declaration=True))
            for number, content in enumerate(self.media, 1):
                archive.writestr(f'word/media/image{number}.png', content)


def add_assets(doc, question, asset_index, staging):
    for number, asset_id in enumerate(question['review_asset_ids'], 1):
        asset = asset_index[asset_id]
        for subnumber, (resource, check) in enumerate(zip(asset['resources'], asset['image_checks']), 1):
            label = f"image {number}" + (f'.{subnumber}' if len(asset['resources']) > 1 else '')
            doc.picture(staging / resource['path'], f"{label} | {asset_id} | {asset['asset_role']} | {asset['source_locator']}", check)
        if not asset['resources']:
            doc.text(f"image {number} | {asset_id} | 未提取独立图像，需要源文档核对", warning=True)


def add_question(doc, row, asset_index, staging, originals, warning_detail=False):
    doc.page_break()
    doc.text('Question ID: ' + row['id'], bold=True)
    doc.text(f"来源：{Path(row['source_file']).name}\n原章节：{row['source_section']}\n原题号：{row['source_question_number']}\n位置：{row['source_locator']}")
    doc.text(f"题型：{row['question_type']}（待人工确认） | {row['review_group']}")
    doc.text('题干', bold=True)
    doc.text(row['stem'])
    doc.text('关联图像（按源位置排序；角色待审核，解析图不参与学生题干渲染）', bold=True)
    add_assets(doc, row, asset_index, staging)
    if row['missing_required_diagram']:
        doc.text('MISSING REQUIRED DIAGRAM — requires_source_check；不得建议approve', bold=True, warning=True)
    if row['options']:
        doc.text('选项', bold=True)
        for label, value in row['options'].items():
            doc.text(label + '. ' + value)
    doc.text('答案（原文；主观题可引用源解答）', bold=True)
    doc.text(row['answer'] or '缺失 — requires_source_check', warning=not bool(row['answer']))
    doc.text('解析 / reference solution', bold=True)
    doc.text(row['reference_solution'] or '缺失 — requires_source_check')
    suggestion = row['knowledge_suggestion']
    doc.text('建议知识点 geometry_v1（按题目目标关键词草标，需人工确认）', bold=True)
    doc.text(f"primary: {suggestion['primary']} {KNOWLEDGE[suggestion['primary']]}\nrelated: " +
             ', '.join(k + ' ' + KNOWLEDGE[k] for k in suggestion['related']) + '\n依据：' + suggestion['basis'])
    doc.text(f"difficulty: {row['difficulty']['suggested']}（待确认）\ndiagram_required: {row['diagram_required']}\nimage_link_confidence: {row['image_link_confidence']}\nformula_status: {row['formula_status']}\nstructure_status: {row['structure_status']}\ndecision: pending")
    if row['warnings']:
        doc.text('人工核对项', bold=True, warning=True)
        for warning in row['warnings']:
            doc.text(f"warning_type: {warning['warning_type']} | warning_field: {warning['warning_field']} | {warning['detail']}", warning=True)
            if warning_detail:
                index = warning.get('paragraph')
                if index:
                    paragraph = originals[row['source_file']][index - 1]
                    original_text = ''.join(n.text or '' for n in paragraph.iter() if n.tag in {W + 't', M + 't'})
                    doc.text(f'原位置：paragraph {index}\noriginal_text（源XML文字，公式结构见下方原生公式）：{original_text}')
                    doc.native_source(paragraph)
                else:
                    original_field = row['raw_candidate'].get(warning['warning_field'], row['raw_candidate']['stem'])
                    doc.text('original_text: ' + original_field)
                doc.text('normalized_text: ' + warning.get('normalized_text', '未进行额外公式归一化或补全'))
                if warning['warning_type'] == 'formula_warning':
                    doc.text('requires_source_check：公式未经猜测或修补；答案仍仅引用源文档。', bold=True, warning=True)
    # Source paragraphs containing math give reviewers exact native OMML,
    # including structures the text extractor cannot normalize.
    if not warning_detail:
        math_paragraphs = [(i, p) for i, p in enumerate(originals[row['source_file']], 1)
                           if row['start_paragraph'] <= i <= row['end_paragraph'] and any(n.tag in {M + 'oMath', M + 'oMathPara'} for n in p.iter())]
        if math_paragraphs:
            doc.text('原文公式核对（原生 OMML；不猜公式）', bold=True)
            for index, paragraph in math_paragraphs:
                doc.text(f'paragraph {index}')
                doc.native_source(paragraph)
    doc.text('人工审核栏', bold=True)
    doc.text('\n'.join('[ ] ' + check for check in CHECKS))
    doc.text('人工备注：\n________________')


def duplicate_report(questions, bank, database):
    reports = {}
    for label, key in [('exact_duplicate', lambda q: json.dumps({k: q['raw_candidate'][k] for k in ['stem', 'answer', 'explanation']}, ensure_ascii=False, sort_keys=True)),
                       ('normalized_text_duplicate', lambda q: normalize_stem(q['raw_candidate']['stem'])),
                       ('same_source_duplicate', lambda q: (q['source_sha256'], q['source_locator']))]:
        groups = defaultdict(list)
        for row in questions:
            groups[key(row)].append(row['id'])
        reports[label] = [ids for ids in groups.values() if len(ids) > 1]
    # Repeated numbering is weaker than same-locator duplication, kept separate.
    numbering = defaultdict(list)
    for row in questions:
        numbering[(row['source_file'], row['source_question_number'])].append(row['id'])
    reports['repeated_source_number'] = [ids for ids in numbering.values() if len(ids) > 1]
    existing = []
    for folder in ['approved', 'candidates']:
        for path in sorted((bank / folder).glob('*.jsonl')):
            existing.extend((str(path), row) for row in read_rows(path))
    database_count = 0
    if database.exists():
        # immutable and mode=ro prevent journaling or accidental mutation.
        if Path(str(database) + '-wal').exists():
            raise ValueError('真实数据库存在 WAL；请在稳定快照下执行只读重复检查')
        connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        connection.row_factory = sqlite3.Row
        try:
            for table_row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                table = table_row['name']
                if 'question' not in table:
                    continue
                quoted = '"' + table.replace('"', '""') + '"'
                columns = {r['name'] for r in connection.execute('PRAGMA table_info(' + quoted + ')')}
                if 'stem' not in columns:
                    continue
                for db_row in connection.execute('SELECT * FROM ' + quoted):
                    row = dict(db_row)
                    for key in ['options', 'correct_answers', 'accepted_answers', 'rubric', 'solution_steps', 'sub_questions']:
                        if isinstance(row.get(key), str):
                            try:
                                row[key] = json.loads(row[key])
                            except json.JSONDecodeError:
                                pass
                    existing.append((f'production:{table}', row))
                    database_count += 1
        finally:
            connection.close()
    fingerprints = defaultdict(list)
    for location, row in existing:
        for digest in {row.get('fingerprint'), content_fingerprint(row)} - {None}:
            fingerprints[digest].append({'id': row.get('id'), 'source': location})
    reports['existing_bank_fingerprint_matches'] = [{'question_id': row['id'], 'matches': fingerprints[row['fingerprint']]}
                                                    for row in questions if row['fingerprint'] in fingerprints]
    reports['existing_records_checked'] = len(existing)
    reports['production_records_checked'] = database_count
    reports['deletions'] = 0
    return reports


def initialize_decisions(path, questions, assets):
    """Append new pending records while preserving any later human decisions."""
    existing = read_rows(path) if path.exists() else []
    keys = {(r['record_type'], r['id']) for r in existing}
    for kind, rows in [('question', questions), ('asset', assets)]:
        for row in rows:
            if (kind, row['id']) not in keys:
                existing.append({'record_type': kind, 'id': row['id'], 'decision': 'pending',
                                 'reviewed_by': None, 'reviewed_at': None, 'notes': '',
                                 'source_sha256': row['source_sha256']})
    write_rows(path, existing)


def verify_docx(path):
    """Check embedded media targets, image order and aspect ratios in saved DOCX."""
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('word/_rels/document.xml.rels'))}
        labels = []
        for inline in root.iter(WP + 'inline'):
            ref = next(inline.iter(A + 'blip')).get(R + 'embed')
            target = 'word/' + rels[ref]
            with Image.open(io.BytesIO(archive.read(target))) as image:
                width, height = image.size
            extent = inline.find(WP + 'extent')
            cx, cy = int(extent.get('cx')), int(extent.get('cy'))
            if cx > 6 * 914400 or abs(cy / cx - height / width) > 0.00001:
                raise ValueError(f'图片比例或页面宽度错误：{path} {ref}')
            labels.append(inline.find(WP + 'docPr').get('name'))
        return {'file': path.name, 'embedded_images': len(labels), 'image_labels': labels,
                'native_math_count': len(list(root.iter(M + 'oMath')))}


def build_review_pack(staging, reports, review_data, decisions, database):
    before = database_snapshot(database)
    questions, assets = read_rows(staging / 'questions.jsonl'), read_rows(staging / 'diagram_assets.jsonl')
    input_hashes = {str(staging / n): file_hash(staging / n) for n in ['questions.jsonl', 'diagram_assets.jsonl']}
    sources = sorted({q['source_file'] for q in questions} | {a['source_file'] for a in assets})
    blocks, originals = {}, {}
    for source in sources:
        blocks[source] = read_docx_blocks(Path(source))
        with ZipFile(source) as archive:
            body = ET.fromstring(archive.read('word/document.xml')).find(W + 'body')
            originals[source] = list(body.iter(W + 'p'))
    reviewed_assets = classify_assets(questions, assets, staging, blocks)
    reviewed_questions = prepare_questions(questions, reviewed_assets, blocks)
    asset_index = {a['id']: a for a in reviewed_assets}
    duplicates = duplicate_report(reviewed_questions, staging.parent, database)
    files = []
    batch_counts = []
    for batch in range(1, 7):
        rows = sorted((q for q in reviewed_questions if q['batch'] == batch),
                      key=lambda q: (int(re.search(r'§7\.(\d+)', q['source_section'])[1]) if '§7.' in q['source_section'] else (13 if '小题' in q['source_section'] else 14), q['start_paragraph']))
        doc = ReviewDocx(f'Geometry 人工审核 Batch{batch:02}（{len(rows)} 条候选）')
        for row in rows:
            add_question(doc, row, asset_index, staging, originals)
        path = reports / f'geometry_review_batch_{batch:02}.docx'
        doc.save(path)
        files.append(path)
        batch_counts.append(len(rows))
    warning_rows = [q for q in reviewed_questions if q['review_group'] == 'warning_candidates']
    doc = ReviewDocx(f'Geometry 警告候选专项审核（{len(warning_rows)} 条；包含 V1.1A 原有警告题）')
    for row in warning_rows:
        add_question(doc, row, asset_index, staging, originals, warning_detail=True)
    path = reports / 'geometry_warning_candidates_review.docx'
    doc.save(path)
    files.append(path)
    unlinked = [a for a in reviewed_assets if a['question_id'] is None]
    doc = ReviewDocx(f'Geometry 未关联图形审核（{len(unlinked)} 个；禁止自动attach）')
    for asset in unlinked:
        doc.page_break()
        doc.text('asset_id: ' + asset['id'], bold=True)
        doc.text(f"source_doc: {Path(asset['source_file']).name}\nparagraph位置: {asset['source_locator']}\n前文: {asset['context_before']}\n当前: {asset['context_at']}\n后文: {asset['context_after']}")
        for number, (resource, check) in enumerate(zip(asset['resources'], asset['image_checks']), 1):
            doc.picture(staging / resource['path'], f'image {number} | ' + asset['id'], check)
        doc.text('候选可能用途：仅参考上方相邻文本，可能为知识说明、章节装饰或题图；程序未绑定。')
        doc.text('人工决定：\n[ ] ignore\n[ ] attach_to_question\n[ ] solution_only\n[ ] decorative\n[ ] unknown\n目标Question ID（仅人工填写）：________________\n人工备注：________________\n当前状态：pending；question_id=null')
    path = reports / 'geometry_unlinked_assets_review.docx'
    doc.save(path)
    files.append(path)
    initialize_decisions(decisions, reviewed_questions, reviewed_assets)
    write_rows(review_data / 'questions_review.jsonl', reviewed_questions)
    write_rows(review_data / 'asset_verification.jsonl', reviewed_assets)
    for group in ['clean_candidates', 'warning_candidates']:
        write_rows(review_data / (group + '.jsonl'), [q for q in reviewed_questions if q['review_group'] == group])
    (review_data / 'duplicate_report.json').write_text(json.dumps(duplicates, ensure_ascii=False, indent=2), encoding='utf-8')
    verifications = [verify_docx(p) for p in files]
    after = database_snapshot(database)
    if before != after:
        raise RuntimeError('真实数据库或sidecar哈希发生变化')
    if any(file_hash(Path(path)) != digest for path, digest in input_hashes.items()):
        raise RuntimeError('V1.1A原始候选数据发生变化')
    roles = Counter(a['asset_role'] for a in reviewed_assets)
    summary = {'clean_candidates': len(reviewed_questions) - len(warning_rows), 'warning_candidates': len(warning_rows),
               'original_warning_candidates': sum(bool(q['extraction_warnings']) for q in questions),
               'batch_counts': batch_counts, 'asset_roles': dict(roles), 'unlinked_assets': len(unlinked),
               'unlinked_pending': len(unlinked), 'missing_required_diagrams': sum(q['missing_required_diagram'] for q in reviewed_questions),
               'duplicate_group_counts': {k: len(v) for k, v in duplicates.items() if isinstance(v, list)},
               'production_db_modified': False, 'database_before': before, 'database_after': after,
               'input_hashes': input_hashes, 'docx_verification': verifications,
               'decision_counts': dict(Counter(r['decision'] for r in read_rows(decisions))),
               'asset_hash_errors': sum(not c['legal'] for a in reviewed_assets for c in a['image_checks'])}
    (review_data / 'review_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# V1.1B Geometry 人工审核包与图形验证', '',
             f"clean_candidates：{summary['clean_candidates']}；warning_candidates：{summary['warning_candidates']}。",
             f"V1.1A 原有警告题 {summary['original_warning_candidates']} 条全部保留，新增检查涵盖答案/解析缺失、非题目边界、低质量图和低置信图题关联。",
             'clean 仅表示程序未检出问题，绝非已完成人工核验。题型、一个primary及related、难度和asset_role均为待人工确认建议。', '',
             '| 批次 | 来源 | 候选数 | 嵌入图像数 |', '|---|---|---:|---:|']
    chapters = ['§7.1 / §7.2', '§7.3 / §7.4', '§7.5 / §7.6', '§7.7 / §7.8', '§7.9 / §7.10', '必刷小题13 / 必刷大题14']
    for index, count in enumerate(batch_counts):
        lines.append(f"| Batch{index+1:02} | {chapters[index]} | {count} | {verifications[index]['embedded_images']} |")
    lines.extend(['', '## 图形验证', '',
                  *[f'- {role}：{roles[role]}（角色草标，尚未人工确认）' for role in ['question_diagram', 'solution_diagram', 'option_image', 'decorative', 'unknown']],
                  f"- 38个未关联图形：{len(unlinked)} 个保持 question_id=null、human_action=pending；无自动绑定。",
                  f"- MISSING REQUIRED DIAGRAM：{summary['missing_required_diagrams']} 条；无批准建议。",
                  f"- 图片原始哈希/解码错误：{summary['asset_hash_errors']}。",
                  '- 已检查369个关联实例的题目段落范围、来源哈希、列表成员关系、表格上下文及跨题媒体复用；逐项证据见 asset_verification.jsonl。',
                  '- 第二张图遗漏检查以源图形占位数量与关联实例数比较；人工仍须核查上下文语义。',
                  '- question_diagram/option_image 为未来学生题干可用角色；solution_diagram仅用于解析。所有student_render_enabled=false。',
                  '- 表格图或角色不明的图形保持unknown；不凭像素/上下文自动认定装饰，decorative需人工确认。',
                  '- 图片按原始比例、150dpi自然宽度显示，最大宽度6英寸、最大高度8英寸。短边<100px或长边<240px显示IMAGE QUALITY WARNING；不放大低分辨率图。',
                  '- TIFF等转为PNG只用于Word嵌入，原始媒体不变；不生成Word页面截图。', '', '## 重复题（仅报告）', '',
                  *[f'- {key}：{value} 组/匹配记录。' for key, value in summary['duplicate_group_counts'].items()],
                  f"- 现有题库检查 {duplicates['existing_records_checked']} 条记录，其中真实数据库只读检查 {duplicates['production_records_checked']} 条；删除0条。",
                  '- same_source_duplicate按同来源哈希+同XML位置；重复题号另列，章节题号重置不视为重复题。',
                  '- exact按题干/答案/解析原文完全相同；normalized按现有normalize_stem规则；fingerprint沿用现有题库实现。', '', '## 审核文件', '',
                  *[f'- [{p.name}]({p.name})' for p in files], '',
                  '## 决策与数据', '',
                  f'- 决策文件：{decisions.as_posix()}；当前分布：{summary["decision_counts"]}。',
                  '- 包含261个question和407个asset决策，首次生成全部pending；重复运行不会覆写已有人工决策。',
                  '- 几何建议体系为geometry_v1，G001–G010；依据题干目标关键词，不使用来源章节自动指定primary。',
                  '- 原始复杂OMML公式直接复制到审核Word作为原文核对材料；未猜测、修补或推导公式/答案。',
                  '- 知识总结误识别、复杂题型和来源已有内嵌答案需人工回源确认，未自动删除任何候选。', '',
                  '## 数据库保护', '', 'production DB是否修改：**NO**。NO migration / NO import / NO attempts changes。',
                  f'- 前后哈希：{json.dumps(before, ensure_ascii=False)}',
                  '- V1.1A候选JSONL、原始DOCX及原始图像只读。没有commit。', '',
                  '## 验证', '',
                  '- 8份Word已检查全部图片关系目标、真实media字节、图像比例及最大宽度；原生OMML保留。',
                  '- 单元测试结果由本次运行完成后追加。',
                  '- 生成命令：python -X utf8 scripts/build_geometry_review_pack.py。', '',
                  '本阶段到此停止，等待人工审核。未进入正式导入或批准。'])
    (reports / 'geometry_v1_1b_review_summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary
