"""Strict geometry-only OMML conversion; no inferred mathematical content."""
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from services.math_normalizer import normalize_math_expression, normalize_math_text, validate_math_expression, FormulaManualReview
from services.source_extractors.docx_question_extractor import M, W, read_docx_blocks


def geometry_math(node):
    """Preserve supported source structures as validated inline LaTeX."""
    def convert(current):
        if current is None:
            raise ValueError('OMML required element missing')
        tag = current.tag.removeprefix(M)
        if current.tag == W + 'rPr' or (current.tag.startswith(M) and (tag.endswith('Pr') or tag == 'ctrlPr')):
            return ''
        if not current.tag.startswith(M):
            raise ValueError('OMML unexpected namespace/content')
        if tag == 't':
            text = current.text or ''
            # These characters are present in the source, never inferred.
            for old, new in {'−': '-', 'π': r'\pi ', 'λ': r'\lambda ', 'θ': r'\theta ',
                             'α': r'\alpha ', 'β': r'\beta ', 'γ': r'\gamma ',
                             '∞': r'\infty ', '≤': r'\leq ', '≥': r'\geq ',
                             '≠': r'\neq ', '×': r'\times ', '·': r'\cdot ', '，': ','}.items():
                text = text.replace(old, new)
            return text
        if tag in {'oMath', 'oMathPara', 'r', 'e', 'num', 'den', 'sup', 'sub', 'deg', 'fName'}:
            return ''.join(convert(child) for child in current)

        def required(name):
            value = convert(current.find(M + name))
            if not value.strip():
                raise ValueError('OMML empty ' + name)
            return value

        if tag == 'f':
            return r'\frac{' + required('num') + '}{' + required('den') + '}'
        if tag in {'sSup', 'sSub', 'sSubSup'}:
            value = required('e')
            if tag in {'sSub', 'sSubSup'}:
                value += '_{' + required('sub') + '}'
            if tag in {'sSup', 'sSubSup'}:
                value += '^{' + required('sup') + '}'
            return value
        if tag == 'rad':
            degree = convert(current.find(M + 'deg')) if current.find(M + 'deg') is not None else ''
            hidden = current.find(M + 'radPr/' + M + 'degHide')
            if not degree and (hidden is None or hidden.get(M + 'val') not in {'1', 'true', 'on'}):
                raise ValueError('OMML visible root degree missing')
            return r'\sqrt' + ('[' + degree + ']' if degree else '') + '{' + required('e') + '}'
        if tag in {'acc', 'bar', 'groupChr'}:
            props = current.find(M + tag + 'Pr')
            char = props.find(M + 'chr') if props is not None else None
            pos = props.find(M + 'pos') if props is not None else None
            value = required('e')
            if tag == 'acc':
                character = char.get(M + 'val') if char is not None else '\u0302'
                if character == '\u0311':
                    return r'\overset{\frown}{' + value + '}'
                command = {'\u20d7': r'\overrightarrow', '\u0302': r'\widehat'}.get(character)
                if command is None:
                    raise ValueError('OMML unsupported accent ' + character)
                return command + '{' + value + '}'
            if tag == 'bar':
                position = pos.get(M + 'val') if pos is not None else 'top'
                if position not in {'top', 'bot'}:
                    raise ValueError('OMML unknown bar position')
                return (r'\overline' if position == 'top' else r'\underline') + '{' + value + '}'
            if char is not None and char.get(M + 'val') == '⏜' and pos is not None and pos.get(M + 'val') == 'top':
                return r'\overset{\frown}{' + value + '}'
            raise ValueError('OMML unsupported group character')
        if tag == 'm':
            rows = current.findall(M + 'mr')
            sizes = {len(row.findall(M + 'e')) for row in rows}
            if not rows or len(sizes) != 1 or 0 in sizes:
                raise ValueError('OMML incomplete matrix')
            values = [[convert(cell) for cell in row.findall(M + 'e')] for row in rows]
            if any(not cell.strip() for row in values for cell in row):
                raise ValueError('OMML empty matrix cell')
            return r'\begin{matrix}' + r' \\ '.join(' & '.join(row) for row in values) + r'\end{matrix}'
        if tag == 'd':
            props = current.find(M + 'dPr')
            def delimiter(name, default):
                child = props.find(M + name) if props is not None else None
                value = child.get(M + 'val', default) if child is not None else default
                allowed = {'': '.', '(': '(', ')': ')', '[': '[', ']': ']', '{': r'\{', '}': r'\}', '|': '|'}
                if value not in allowed:
                    raise ValueError('OMML unsupported delimiter ' + value)
                return allowed[value]
            values = current.findall(M + 'e')
            if len(values) != 1:
                raise ValueError('OMML multiple delimiter expressions require review')
            return r'\left' + delimiter('begChr', '(') + convert(values[0]) + r'\right' + delimiter('endChr', ')')
        if tag == 'func':
            return required('fName') + r'\left(' + required('e') + r'\right)'
        raise ValueError('OMML unsupported structure ' + tag)

    value = convert(node)
    if not value.strip():
        raise ValueError('OMML empty formula')
    value = normalize_math_expression(value, preserve_latex=True)
    if not validate_math_expression(value)['valid']:
        raise ValueError('OMML invalid formula')
    return '$' + value + '$'


def normalize_geometry_text(text):
    """Normalize source math/prose separately, then join adjacent math spans.

    Delimiters here were added by our XML reader. A prose '=' run between two
    OMML runs is preserved inside their combined expression, never evaluated.
    """
    marks = list(re.finditer(r'[（(]\s*[√×]\s*[）)]', text))
    if marks:
        parts, cursor = [], 0
        for match in marks:
            parts.extend((normalize_geometry_text(text[cursor:match.start()]), match[0]))
            cursor = match.end()
        parts.append(normalize_geometry_text(text[cursor:]))
        return ''.join(parts)
    if re.match(r'^\s*[ABCD][.．、]', text):
        # Source option labels are structural, not part of an adjacent formula.
        pieces = re.split(r'(?<![A-Za-z])([ABCD][.．、])', text)
        return ''.join(part + ' ' if i % 2 else normalize_geometry_text(part)
                       for i, part in enumerate(pieces))
    if text.count('$') % 2:
        raise FormulaManualReview('source_dollar_mismatch')
    parts = text.split('$')
    normalized = ''.join('$' + normalize_math_expression(part, preserve_latex=True) + '$'
                         if i % 2 else normalize_math_text(part) for i, part in enumerate(parts))
    while re.search(r'\$([^$]+)\$\$([^$]+)\$', normalized):
        normalized = re.sub(r'\$([^$]+)\$\$([^$]+)\$', lambda m: '$' + m[1] + m[2] + '$', normalized)
    return normalized


def read_geometry_blocks(path):
    # OMML is one explicit expression, including Chinese labels, angles and
    # matrix cells. Keep its delimiter so prose parsing cannot split it.
    blocks = read_docx_blocks(path, math_converter=geometry_math)
    with ZipFile(path) as archive:
        paragraphs = list(ET.fromstring(archive.read('word/document.xml')).find(W + 'body').iter(W + 'p'))
    for block, paragraph in zip(blocks, paragraphs):
        for run in paragraph.iter(W + 'r'):
            fonts = run.find(W + 'rPr/' + W + 'rFonts')
            text = ''.join(t.text or '' for t in run.iter(W + 't'))
            if fonts is not None and text and any(font.lower() in {'gbk_s', 'symbol', 'wingdings', 'mt extra'} for font in fonts.attrib.values()):
                block['warnings'].append('公式符号字体无法确定Unicode数学语义：' + ','.join(sorted(set(fonts.attrib.values()))) + ' / ' + text)
    for block in blocks:
        text = block['text']
        # Word explicitly styles these as subscripts. Preserve Chinese/triangle
        # labels as literal text rather than dropping them at a prose boundary.
        text = re.sub(r'([A-Za-zΑ-Ωα-ω])_\(([^()]*(?:[\u4e00-\u9fff△])[^()]*)\)',
                      lambda m: '$' + m[1] + r'_{\text{' + m[2] + '}}$', text)
        try:
            block['text'] = normalize_geometry_text(text)
        except FormulaManualReview as error:
            block['text'] = text
            block['warnings'].append('源公式排版仍无法可靠恢复：' + str(error))
    return blocks
