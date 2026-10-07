"""Shared safe rendering of canonical prose plus inline LaTeX.

Legacy parsing primitives remain for deterministic normalization. Mathematical
meaning is never evaluated here; invalid formulas render a safe placeholder.
"""
import re

TOKENS = re.compile(r'√|\([^()\n]+\)|[A-Za-z][A-Za-z0-9]*|\d+(?:\.\d+)?')
EXISTING_MATH = re.compile(r'(\$\$[\s\S]*?\$\$|\$[^$\n]+\$)')


def _group(text, start):
    if start >= len(text) or text[start] != '(':
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == '(':
            depth += 1
        elif text[index] == ')':
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    return None


def _latex(text, depth):
    parts = _parts(text, depth + 1)
    return ''.join(value for _, value in parts).replace('×', r'\times ').replace('π', r'\pi ')


def _expression(text, match, depth):
    token, end = match.group(), match.end()
    converted = False
    latex = token
    if token in ('sqrt', '√', 'root'):
        group = _group(text, end)
        if group and group[0].strip():
            value, end = group
            if token == 'root':
                comma = None
                nesting = 0
                for index, char in enumerate(value):
                    nesting += int(char == '(') - int(char == ')')
                    if char == ',' and nesting == 0:
                        if comma is not None:
                            return None
                        comma = index
                if comma is None or not value[:comma].strip() or not value[comma + 1:].strip():
                    return None
                latex = r'\sqrt[' + _latex(value[:comma], depth) + ']{' + _latex(value[comma + 1:], depth) + '}'
            else:
                latex = r'\sqrt{' + _latex(value, depth) + '}'
            converted = True
    while end < len(text) and text[end] in '^_':
        marker = text[end]
        group = _group(text, end + 1)
        if group and group[0].strip():
            value, next_end = group
        elif end + 1 < len(text) and re.fullmatch(r'[A-Za-z0-9]', text[end + 1]):
            value, next_end = text[end + 1], end + 2
            if next_end < len(text) and text[next_end].isalnum():
                break  # Ambiguous ungrouped multi-character exponent/index.
        else:
            break
        latex = (r'\log' if latex == 'log' else latex) + marker + '{' + _latex(value, depth) + '}'
        end, converted = next_end, True
    if converted and token == 'log':
        group = _group(text, end)
        atom = TOKENS.match(text, end)
        if group:
            latex += '(' + _latex(group[0], depth) + ')'
            end = group[1]
        elif atom:
            latex += ' ' + atom.group()
            end = atom.end()
    return (latex, end) if converted else None


def _parts(text, depth=0):
    if depth > 12:
        return [(False, text)]
    parts, cursor = [], 0
    for match in TOKENS.finditer(text):
        if match.start() < cursor:
            continue
        parsed = _expression(text, match, depth)
        if parsed is None:
            continue
        latex, end = parsed
        if cursor < match.start():
            parts.append((False, text[cursor:match.start()]))
        parts.append((True, latex))
        cursor = end
    if cursor < len(text):
        parts.append((False, text[cursor:]))
    return parts


def math_markdown(text: str) -> str:
    """Render the canonical format once; invalid math gets a safe placeholder."""
    from services.math_normalizer import normalize_math_text, FormulaManualReview
    import logging
    try:
        text = normalize_math_text(text)
    except FormulaManualReview as error:
        logging.getLogger(__name__).warning('Formula rendering blocked: %s', error)
        return '[公式需要修复]'
    result = []
    for index,chunk in enumerate(text.split('$')):
        if index % 2:
            result.append('$'+chunk+'$')
        else:
            result.append(re.sub(r'([\\`*_{}\[\]<>])', r'\\\1', chunk).replace('\n', '  \n'))
    return ''.join(result)


def render_math_text(text: str):
    """One Streamlit renderer shared by all question and solution displays."""
    import streamlit as st
    st.markdown(math_markdown(text), unsafe_allow_html=False)
