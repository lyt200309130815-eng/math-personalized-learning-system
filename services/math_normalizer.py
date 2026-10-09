"""Canonical question text: prose plus single-dollar inline LaTeX fragments.

Conversions are notation changes only. Unknown fused roots are never inferred.
Machine grading uses a separate deterministic adapter, not display formatting.
"""
from copy import deepcopy
import re
FUSED_ROOT=re.compile(r'\b[A-Za-z]+(?:root|sqrt)\s*\(')


class FormulaManualReview(ValueError):
    status = 'formula_manual_review'


def _balanced(text, opening='{', closing='}'):
    depth = 0
    for i,c in enumerate(text):
        if i and text[i-1] == '\\': continue
        if c == opening: depth += 1
        elif c == closing:
            depth -= 1
            if depth < 0: return False
    return depth == 0


def _brace_group(text, pos):
    while pos < len(text) and text[pos].isspace(): pos += 1
    if pos >= len(text) or text[pos] != '{': return None
    depth = 0
    for end in range(pos,len(text)):
        if text[end] == '{': depth += 1
        elif text[end] == '}':
            depth -= 1
            if depth == 0: return text[pos+1:end],end+1
    return None


def validate_math_expression(expr):
    """Return syntax findings without evaluating any mathematical statement."""
    issues=[]
    if not _balanced(expr): issues.append('unclosed_brace')
    if '$' in expr or '\\(' in expr or '\\[' in expr: issues.append('delimiter_conflict')
    if FUSED_ROOT.search(expr): issues.append('unknown_fused_root')
    if re.search(r'(?<!\\)\b(?:root|sqrt)\s*\(|\^\(|_\(',expr): issues.append('docx_intermediate_notation')
    if re.search(r'\[(?:公式|图片|选项边界)待核\]|OMML|oMath|m:sSup|�',expr): issues.append('extraction_marker')
    for m in re.finditer(r'\\frac\b',expr):
        first=_brace_group(expr,m.end())
        second=_brace_group(expr,first[1]) if first else None
        if not first or not second or not first[0].strip() or not second[0].strip(): issues.append('invalid_frac')
    for m in re.finditer(r'\\sqrt\b',expr):
        pos=m.end()
        if pos < len(expr) and expr[pos]=='[':
            end=expr.find(']',pos)
            if end<0 or not expr[pos+1:end].strip(): issues.append('invalid_sqrt');continue
            pos=end+1
        group=_brace_group(expr,pos)
        if not group or not group[0].strip(): issues.append('invalid_sqrt')
    if re.search(r'[\^_]\s*(?:$|\{\s*\})',expr): issues.append('missing_script')
    if re.search(r'(?:^|\{)\s*[\^_]',expr): issues.append('missing_script_base')
    if expr.count(r'\begin{') != expr.count(r'\end{'): issues.append('unclosed_environment')
    # Commands outside this deliberately small educational vocabulary require
    # review rather than sending unsupported macros to KaTeX.
    allowed=set('frac sqrt log ln lg sin cos tan pi infty times div cdot leq geq ne neq in notin cup cap emptyset varnothing setminus mathbb mathrm text left right begin end cases aligned quad qquad pm mp alpha beta gamma delta theta lambda mu rho sigma omega Delta Sigma cdots ldots overline underline abs lvert rvert lbrace rbrace vec overrightarrow widehat overset frown matrix'.split())
    for command in re.findall(r'\\([A-Za-z]+)',expr):
        if command not in allowed: issues.append('unsupported_command:'+command)
    return {'valid':not issues,'issues':list(dict.fromkeys(issues))}


def _fractions(expr):
    from services.math_text import _group
    out=[];pos=0
    while pos < len(expr):
        group=_group(expr,pos)
        if group:
            numerator,end=group
            if expr[end:end+2]=='/(':
                denominator=_group(expr,end+1)
                if denominator and numerator.strip() and denominator[0].strip():
                    out.append(r'\frac{'+_fractions(numerator)+'}{'+_fractions(denominator[0])+'}')
                    pos=denominator[1];continue
        out.append(expr[pos]);pos+=1
    return ''.join(out)


def normalize_math_expression(expr, *, preserve_latex=False):
    """Convert explicit extractor notation to unwrapped LaTeX, or refuse it."""
    if not isinstance(expr,str): raise FormulaManualReview('not_text')
    if FUSED_ROOT.search(expr): raise FormulaManualReview('unknown_fused_root')
    if '$' in expr: raise FormulaManualReview('delimiter_conflict')
    if not _balanced(expr): raise FormulaManualReview('unclosed_brace')
    if preserve_latex and validate_math_expression(expr)['valid']:return expr
    if re.search(r'\^\d{2,}',expr):raise FormulaManualReview('ambiguous_ungrouped_exponent')
    from services.math_text import _group
    for match in re.finditer(r'(?<!\\)(?:log|ln|lg)(?:_\(|\()',expr):
        base=_group(expr,match.end()-1)
        if base:
            arg=_group(expr,base[1]) if expr[match.start():].startswith('log_') else base
            if arg and expr[arg[1]:arg[1]+2]=='/(':
                raise FormulaManualReview('ambiguous_log_fraction_scope')
    # Preserve literal sets/case braces in legacy notation; TeX grouping must
    # never silently hide their visible delimiters.
    if '\\' not in expr and not re.search(r'[\^_]\{',expr):
        expr=expr.replace('{',r'\{').replace('}',r'\}')
    value=_rewrite_notation(expr)
    value=_fractions(value)
    value=re.sub(r'\^(?P<v>-?\d+|[A-Za-z])(?![A-Za-z0-9{])',lambda m:'^{'+m['v']+'}',value)
    for old,new in {'−':'-','×':r'\times ','÷':r'\div ','≤':r'\leq ','≥':r'\geq ','≠':r'\neq ','∈':r'\in ','∪':r'\cup ','∞':r'\infty ','π':r'\pi '}.items():
        value=value.replace(old,new)
    findings=validate_math_expression(value)
    if not findings['valid']: raise FormulaManualReview(', '.join(findings['issues']))
    return value


def _rewrite_notation(expr,depth=0):
    from services.math_text import _group
    if depth>20:raise FormulaManualReview('formula_nesting_limit')
    out=[];pos=0
    while pos<len(expr):
        if expr[pos] in '^_' and expr[pos+1:pos+2]=='(':
            group=_group(expr,pos+1)
            if not group or not group[0].strip():raise FormulaManualReview('incomplete_script')
            out.append(expr[pos]+'{'+_rewrite_notation(group[0],depth+1)+'}');pos=group[1];continue
        root=re.match(r'(sqrt|root|√)\(',expr[pos:])
        if root and (not pos or not expr[pos-1].isalpha()):
            group=_group(expr,pos+len(root[1]))
            if not group or not group[0].strip():raise FormulaManualReview('incomplete_root')
            if root[1]=='root':
                level=0;commas=[]
                for i,c in enumerate(group[0]):
                    level+=(c=='(')-(c==')')
                    if c==',' and level==0:commas.append(i)
                if len(commas)!=1:raise FormulaManualReview('unknown_root_arguments')
                split=commas[0];degree=group[0][:split];argument=group[0][split+1:]
                if not degree.strip() or not argument.strip():raise FormulaManualReview('empty_root')
                out.append(r'\sqrt['+_rewrite_notation(degree,depth+1)+']{'+_rewrite_notation(argument,depth+1)+'}')
            else:out.append(r'\sqrt{'+_rewrite_notation(group[0],depth+1)+'}')
            pos=group[1];continue
        out.append(expr[pos]);pos+=1
    value=''.join(out)
    value=re.sub(r'(?<![A-Za-z\\])log(?=_)',lambda m:r'\log',value)
    value=re.sub(r'(\\log_\{[^{}]+\})(?=[A-Za-z0-9])',r'\1 ',value)
    return value


SPAN=re.compile(r"[A-Za-z0-9\\^_{}()[\].,'，+*/=<>!|;:\-−×÷≤≥≠∈∪∞π√Α-Ωα-ω△±·\s]+")


def normalize_math_text(text):
    """Canonicalize prose/math once, preserving valid existing inline LaTeX."""
    if not isinstance(text,str): raise FormulaManualReview('not_text')
    if '$' not in text:
        text=re.sub(r'\b([A-Za-z])\\\{([0-9,，\s+\-]+)\}',lambda m:'$'+m[1]+r'\setminus\{'+m[2].replace('，',',')+r'\}$',text)
    if not _balanced(text):raise FormulaManualReview('unclosed_brace')
    # Complete alternative delimiters can be translated safely; malformed or
    # nested environments are quarantined.
    text=re.sub(r'\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)',lambda m:'$'+(m[1] if m[1] is not None else m[2])+'$',text)
    if '$$$' in text: raise FormulaManualReview('repeated_delimiter')
    text=re.sub(r'\$\$([^$]+)\$\$',lambda m:'$'+m[1].strip()+'$',text)
    if '$$' in text or text.count('$')%2: raise FormulaManualReview('isolated_dollar')
    result=[]
    for index,chunk in enumerate(text.split('$')):
        if index%2:
            checked=normalize_math_expression(chunk,preserve_latex=True)
            result.append('$'+checked+'$');continue
        def convert(m):
            value=m[0];stripped=value.strip()
            if re.search(r'</?[A-Za-z]{2,}\s*>',stripped):return value
            label=re.match(r'^([A-D]\.\s+)(.+)$',value)
            if label:return label[1]+normalize_math_text(label[2])
            trigger=re.search(r'[\^_=/<>≤≥≠∈∪×÷]|(?:sqrt|root)\(|\\[A-Za-z]|√',stripped)
            if not trigger:return value
            lead=value[:len(value)-len(value.lstrip())];tail=value[len(value.rstrip()):]
            return lead+'$'+normalize_math_expression(stripped.replace('，',','))+'$'+tail
        result.append(SPAN.sub(convert,chunk))
    normalized=''.join(result)
    if FUSED_ROOT.search(normalized) or re.search(r'\^\(|_\(|\b(?:root|sqrt)\s*\(',normalized):
        raise FormulaManualReview('residual_intermediate_notation')
    return normalized


FIELDS=('stem','options','explanation','canonical_answer','answer_expression','accepted_answers',
        'reference_answer','reference_answers_by_subquestion','solution_steps','rubric','sub_questions','hints')


def audit_question(question):
    """Check all mathematical content, including nested answer/rubric fields."""
    normalized=deepcopy(question);changes=[];issues=[]
    def visit(value,path):
        if isinstance(value,str):
            try:
                updated=normalize_math_text(value)
                if updated!=value: changes.append({'field':path,'original':value,'normalized':updated,'issue':'legacy_notation','safe':True})
                return updated
            except FormulaManualReview as error:
                issues.append({'field':path,'original':value,'issue':str(error),'safe':False});return value
        if isinstance(value,list):return [visit(v,f'{path}[{i}]') for i,v in enumerate(value)]
        if isinstance(value,dict):return {k:visit(v,f'{path}.{k}') for k,v in value.items()}
        return value
    for field in FIELDS:
        if field in normalized:normalized[field]=visit(normalized[field],field)
    return {'formula_status':'formula_manual_review' if issues else 'valid','normalized':normalized,'changes':changes,'issues':issues}


def evaluator_math_text(text):
    """Translate validated canonical LaTeX into the evaluator's small grammar."""
    text=normalize_math_text(text).replace('$','')
    def groups(value):
        while True:
            match=re.search(r'\\frac\b|\\sqrt\b',value)
            if not match:break
            kind=match[0];pos=match.end()
            if kind==r'\sqrt' and value[pos:pos+1]=='[':raise FormulaManualReview('indexed_root_grading_requires_review')
            first=_brace_group(value,pos)
            if not first:raise FormulaManualReview('invalid_group')
            if kind==r'\frac':
                second=_brace_group(value,first[1])
                if not second:raise FormulaManualReview('invalid_frac')
                replacement='('+groups(first[0])+')/('+groups(second[0])+')';end=second[1]
            else:replacement='sqrt('+groups(first[0])+')';end=first[1]
            value=value[:match.start()]+replacement+value[end:]
        return value
    text=groups(text)
    for old,new in {r'\infty':'inf',r'\pi':'pi',r'\cup':'∪',r'\times':'*',r'\cdot':'*',r'\div':'/',r'\leq':'≤',r'\geq':'≥',r'\neq':'≠',r'\{':'{',r'\}':'}'}.items():text=text.replace(old,new)
    text=re.sub(r'\^\{([^{}]+)\}',r'^(\1)',text)
    return text.strip()
