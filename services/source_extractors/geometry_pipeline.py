"""Offline geometry staging: original assets and positional links, never approval."""
import hashlib
import json
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from services.source_extractors.docx_question_extractor import W, R, read_docx_blocks

QUESTION = re.compile(r'^(?:例\s*\d+|跟踪训练\s*\d+|\d+[.．、](?!\d))')
HEADER = re.compile(r'^(?:题型|思维升华|重点解读|方法总结|课时|考点|感悟|防范)')
VISUAL = {W + 'drawing', W + 'pict', W + 'object'}


def scan_docx(path: Path) -> dict:
    """Count package media separately from visual occurrences across Word parts."""
    with ZipFile(path) as archive:
        roots = [ET.fromstring(archive.read(n)) for n in archive.namelist()
                 if n.startswith('word/') and n.endswith('.xml')]
        return {'file': path.name, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'embedded_media_count': sum(n.startswith('word/media/') and not n.endswith('/')
                                            for n in archive.namelist()),
                'drawing_count': sum(len(list(root.iter(W + 'drawing'))) for root in roots),
                'pict_count': sum(len(list(root.iter(W + 'pict'))) for root in roots),
                'object_count': sum(len(list(root.iter(W + 'object'))) for root in roots)}


def extract_geometry(path: Path, output: Path) -> tuple[list, list]:
    """Keep conservative question boundaries and exact paragraph/drawing locators.

    Associations are drafts. Headers terminate questions; introductory visuals
    remain unassigned. Solution visuals never silently become stem diagrams.
    """
    blocks = read_docx_blocks(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    questions, assets = [], []
    active = None
    role = 'unassigned'
    owners = {}
    for block in blocks:
        text = block['text']
        if HEADER.match(text):
            active = None
            role = 'unassigned'
        if QUESTION.match(text):
            active = {'id': 'GQ-' + hashlib.sha256((digest + ':' + str(block['index'])).encode()).hexdigest()[:20],
                      'taxonomy_version': 'geometry_v1', 'source_file': path.as_posix(),
                      'source_sha256': digest, 'source_question_number': QUESTION.match(text)[0],
                      'start_paragraph': block['index'], 'end_paragraph': block['index'],
                      'stem': '', 'answer': '', 'explanation': '', 'asset_ids': [],
                      'quality_status': 'draft', 'review_status': 'pending_review',
                      'primary_knowledge_point_id': None, 'extraction_warnings': []}
            questions.append(active)
            role = 'stem'
        if active is not None:
            if re.match(r'^答案', text):
                role = 'answer'
            elif re.match(r'^(?:解析|解|证明)(?:\s|[:：])', text):
                role = 'explanation'
            active[role] += text + '\n'
            active['end_paragraph'] = block['index']
            active['extraction_warnings'].extend(block['warnings'])
            owners[block['index']] = (active, role)

    with ZipFile(path) as archive:
        names = set(archive.namelist())
        rel_name = 'word/_rels/document.xml.rels'
        relations = {rel.get('Id'): rel for rel in ET.fromstring(archive.read(rel_name))} if rel_name in names else {}
        root = ET.fromstring(archive.read('word/document.xml'))
        body = root.find(W + 'body')
        for index, paragraph in enumerate(body.iter(W + 'p'), 1):
            # Top-level visual containers prevent double counting nested objects.
            def visuals(node):
                for child in node:
                    if child.tag in VISUAL:
                        yield child
                    else:
                        yield from visuals(child)
            for number, visual in enumerate(visuals(paragraph), 1):
                question, asset_role = owners.get(index, (None, 'unassigned'))
                locator = f'word/document.xml paragraph {index} visual {number}'
                asset_id = 'GA-' + hashlib.sha256((digest + locator).encode()).hexdigest()[:20]
                directory = output / 'assets' / asset_id
                directory.mkdir(parents=True, exist_ok=True)
                (directory / 'drawing.xml').write_bytes(ET.tostring(visual, encoding='utf-8'))
                resources, issues = [], []
                refs = sorted({value for node in visual.iter() for key, value in node.attrib.items()
                               if key in {R + 'embed', R + 'id', R + 'link'}})
                for ref in refs:
                    rel = relations.get(ref)
                    if rel is None or rel.get('TargetMode') == 'External':
                        issues.append(f'无法提取或为外部关系：{ref}')
                        continue
                    target = posixpath.normpath(posixpath.join('word', rel.get('Target', ''))).lstrip('/')
                    if not target.startswith('word/media/') or target not in names:
                        issues.append(f'非独立媒体或缺失：{ref}')
                        continue
                    content = archive.read(target)
                    asset_path = directory / (ref + Path(target).suffix.lower())
                    asset_path.write_bytes(content)
                    resources.append({'relationship_id': ref, 'package_part': target,
                                      'path': asset_path.relative_to(output).as_posix(),
                                      'sha256': hashlib.sha256(content).hexdigest()})
                row = {'id': asset_id, 'source_file': path.as_posix(), 'source_sha256': digest,
                       'source_locator': locator, 'question_id': question['id'] if question else None,
                       'role': asset_role, 'association_status': 'pending_review',
                       'extraction_method': 'embedded_media' if resources and not issues else 'page_render_fallback',
                       'review_status': 'pending_review', 'quality_status': 'draft',
                       'resources': resources, 'drawing_xml': (directory / 'drawing.xml').relative_to(output).as_posix(),
                       'warnings': issues, 'page_render_generated': False}
                assets.append(row)
                if question:
                    question['asset_ids'].append(asset_id)
    for question in questions:
        question['source_locator'] = f"word/document.xml paragraphs {question['start_paragraph']}–{question['end_paragraph']}"
        question['extraction_warnings'] = sorted(set(question['extraction_warnings']))
        question['question_type'] = 'choice_pending_review' if re.search(r'[ABCD][.．、]', question['stem']) else 'pending_review'
        if re.search(r'如图|下图|图中|图示', question['stem']) and not any(
                a['question_id'] == question['id'] and a['role'] == 'stem' for a in assets):
            question['extraction_warnings'].append('题干引用图形但未提取到题干图，需人工核对')
    return questions, assets


def build_pipeline(source: Path, output: Path) -> dict:
    """Write reviewable staging artifacts only; no database access or rendering."""
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents:
        raise ValueError('输出目录不能位于原始资料目录中')
    files = sorted(p for p in source.rglob('*') if p.suffix.lower() == '.docx' and not p.name.startswith('~$'))
    if not files:
        raise ValueError('未找到 DOCX 文件')
    output.mkdir(parents=True, exist_ok=True)
    scans, questions, assets = [], [], []
    for path in files:
        scans.append(scan_docx(path))
        extracted, diagrams = extract_geometry(path, output)
        questions.extend(extracted)
        assets.extend(diagrams)
    summary = {'docx_count': len(files), 'files': scans, 'candidate_count': len(questions),
               'asset_count': len(assets), 'unassigned_asset_count': sum(a['question_id'] is None for a in assets),
               'fallback_count': sum(a['extraction_method'] == 'page_render_fallback' for a in assets),
               'approved_count': 0, 'database_imported': False}
    for name, rows in [('questions.jsonl', questions), ('diagram_assets.jsonl', assets),
                       ('review_queue.jsonl', [{'record_type': 'question', **q} for q in questions] +
                        [{'record_type': 'asset', **a} for a in assets])]:
        (output / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    (output / 'scan_report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary
