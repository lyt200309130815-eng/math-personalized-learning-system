"""Read DOCX XML in order, preserving supported math and flagging loss."""

from dataclasses import dataclass, asdict
import hashlib
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from services.question_validator import content_fingerprint, validate_candidate

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass
class CandidateQuestion:
    """Unapproved, traceable candidate; XML paragraph positions are not page numbers."""
    id: str
    stem: str
    options: dict
    answer: str
    explanation: str
    taxonomy_version: str
    primary_knowledge_point_id: str | None
    related_knowledge_point_ids: list
    question_prerequisite_ids: list
    difficulty: int
    ability_tags: list
    method_tags: list
    estimated_time: int
    source_type: str
    source_file: str
    source_section: str
    source_question_number: str | None
    source_locator: str
    extraction_status: str
    quality_status: str
    review_notes: list
    fingerprint: str
    version: int
    extraction_warnings: list
    image_resources: list
    annotation_status: str = "pending_review"

    def to_dict(self):
        return asdict(self)


def _math(node):
    """Convert a deliberately small OMML subset; never flatten unknown structure."""
    tag = node.tag.removeprefix(M)
    if tag.endswith("Pr") or tag in {"ctrlPr"}:
        return ""
    if tag == "t":
        return node.text or ""
    if tag in {"oMath", "oMathPara", "r", "e", "num", "den", "sup", "sub", "deg", "fName"}:
        return "".join(_math(child) for child in node)
    if tag == "func":
        name, argument = _math(node.find(M + "fName")), _math(node.find(M + "e"))
        if not name or not argument:
            raise ValueError("函数公式部分缺失")
        return name + "(" + argument + ")"
    if tag == "f":
        numerator, denominator = _math(node.find(M+'num')), _math(node.find(M+'den'))
        if not numerator or not denominator: raise ValueError("分式部分缺失")
        return f"({numerator})/({denominator})"
    if tag in {"sSup", "sSub", "sSubSup"}:
        text = _math(node.find(M + "e"))
        if not text or text == "()": raise ValueError("上下标主体缺失")
        if tag in {"sSub", "sSubSup"}:
            text += f"_({_math(node.find(M+'sub'))})"
        if tag in {"sSup", "sSubSup"}:
            text += f"^({_math(node.find(M+'sup'))})"
        return text
    if tag == "rad":
        degree = node.find(M + "deg")
        deg = _math(degree) if degree is not None else ""
        argument = _math(node.find(M + "e"))
        if not argument:
            raise ValueError("根式主体缺失")
        return f"root({deg},{argument})" if deg else f"sqrt({argument})"
    if tag == "d":
        props = node.find(M + "dPr")
        left, right = "(", ")"
        if props is not None:
            for name, default in (("begChr", "("), ("endChr", ")")):
                child = props.find(M + name)
                value = child.get(M + "val", default) if child is not None else default
                if name == "begChr": left = value
                else: right = value
        values = node.findall(M + "e")
        if len(values) != 1:
            raise ValueError("多表达式定界符暂不支持")
        # Word often encodes a piecewise expression/inequality system as a
        # one-column matrix under a left brace. Preserve every row; never
        # flatten arbitrary matrices or infer missing conditions.
        matrix = values[0].find(M + "m")
        if matrix is not None and left == "{" and right in {"", "}"}:
            rows = matrix.findall(M + "mr")
            if not rows or any(len(row.findall(M + "e")) != 1 for row in rows):
                raise ValueError("分段公式只支持完整单列结构")
            texts = [_math(row.find(M + "e")) for row in rows]
            if any(not text.strip() for text in texts):
                raise ValueError("分段公式行缺失")
            return "{" + "; ".join(texts) + "}"
        return left + _math(values[0]) + right
    raise ValueError(f"OMML结构暂不支持：{tag}")


def read_docx_blocks(path: str | Path) -> list[dict]:
    """Return ordered paragraphs, including table cell paragraphs and XML locators."""
    path = Path(path)
    if path.name.startswith("~$"):
        return []
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        relations = {}
        if "word/_rels/document.xml.rels" in archive.namelist():
            for rel in ET.fromstring(archive.read("word/_rels/document.xml.rels")):
                relations[rel.get("Id")] = rel.get("Target")
        blocks = []
        body = root.find(W + "body")
        for index, paragraph in enumerate(body.iter(W + "p"), 1):
            warnings, images = [], []

            def render(node):
                if node.tag in {M + "oMath", M + "oMathPara"}:
                    try:
                        return _math(node)
                    except (ValueError, AttributeError, TypeError):
                        warnings.append("包含无法可靠转换的 OMML 公式")
                        return "[公式待核]"
                if node.tag in {W + "drawing", W + "pict", W + "object"}:
                    refs = [relations[value] for child in node.iter() for key, value in child.attrib.items()
                            if key in {R + "embed", R + "id"} and value in relations]
                    images.extend(refs or ["XML嵌入对象"])
                    return "[图片待核]"
                if node.tag == W + "r":
                    text = "".join(render(child) for child in node if child.tag != W + "rPr")
                    script = node.find(W + "rPr/" + W + "vertAlign")
                    if script is not None and text:
                        kind = script.get(W + "val")
                        if kind == "superscript": return f"^({text})"
                        if kind == "subscript": return f"_({text})"
                    return text
                if node.tag == W + "t": return node.text or ""
                if node.tag in {W + "sym", W + "instrText"}:
                    warnings.append("符号字体或域公式需要人工核对")
                    return "[公式待核]"
                if node.tag in {W + "tab", W + "br", W + "cr"}: return " "
                return "".join(render(child) for child in node)

            text = render(paragraph).strip()
            # A single styled exponent/subscript can span multiple Word runs.
            previous = None
            while previous != text:
                previous = text
                text = re.sub(r"\^\(([^()]*)\)\^\(([^()]*)\)", lambda match: "^(" + match[1] + match[2] + ")", text)
                text = re.sub(r"_\(([^()]*)\)_\(([^()]*)\)", lambda match: "_(" + match[1] + match[2] + ")", text)
            # A table flattened into text loses row/column semantics; mark it unsafe.
            blocks.append({"text": text, "index": index, "warnings": warnings, "images": images,
                           "xml": paragraph})
        table_paragraph_ids = {id(p) for table in body.iter(W + "tbl") for p in table.iter(W + "p")}
        for block in blocks:
            if id(block.pop("xml")) in table_paragraph_ids:
                block["warnings"].append("表格结构需人工核对")
        return blocks


START = re.compile(r"^(?:(?:例|跟踪训练)\s*\d+[\s．.、]*)?(?:\([12]\)|（[12]）)(?![/^])|^(?:例|跟踪训练)\s*\d+|^\d+[.．、](?!\d)")
OPTION = re.compile(r"(?<![A-Za-z])([ABCD])[.．、]\s*")


def _annotation(stem, explanation, section):
    """Conservative keyword draft; all inferred labels await human review."""
    text = stem + "\n" + explanation
    rules = [("K015", r"成本|利润|计费|增长率|模型|药物|人口"),
             ("K005", r"奇函数|偶函数|奇偶"), ("K006", r"周期|中心对称|对称中心"),
             ("K004", r"最大值|最小值|最值|恒成立|恒非负"),
             ("K003", r"单调|递增|递减"), ("K013", r"零点|二分法|根的个数|方程的解"),
             ("K011", r"大小比较|大小关系|从小到大|从大到小"), ("K002", r"定义域|值域|分段函数|解析式"),
             ("K010", r"对数|log|ln\s"), ("K009", r"指数函数|指数运算"),
             ("K008", r"幂函数"), ("K007", r"二次函数|抛物线"),
             ("K012", r"平移|伸缩|翻折|图象|图像"), ("K001", r"函数|对应")]
    # Prefer the stem over explanation when identifying the tested objective.
    primary = next((key for key, pattern in rules if re.search(pattern, stem)), None)
    if primary is None:
        primary = next((key for key, pattern in rules if re.search(pattern, section)), None)
    if primary == "K001":
        section_rules = [("K014", "函数与方程的综合应用"), ("K015", "函数模型"),
                         ("K006", "周期性"), ("K003", "单调性"), ("K002", "概念及其表示")]
        primary = next((key for key, word in section_rules if word in section), primary)
    if "周期" in stem or "中心对称" in stem or "对称中心" in stem or "关于直线" in stem:
        primary = "K006"
    if "平移" in stem or "伸缩" in stem or "翻折" in stem:
        primary = "K012"
    if "反函数" in stem:
        primary = "K010" if "指数" in stem else "K002"
    if re.search(r"交点|根的个数|零点", stem):
        primary = "K014" if "综合应用" in section else "K013"
    if "单调性与最值" in section and primary == "K004" and not re.search(r"最大值|最小值|最值", stem):
        primary = "K003"
    if primary == "K001":
        if re.search(r"奇函数|偶函数|奇偶", explanation):
            primary = "K005"
        elif re.search(r"f\([^)]*\).*等于|f\([^)]*\).*的值", stem):
            primary = "K002"
    if "指、对、幂的大小比较" in section and primary in {"K008", "K009", "K010"}:
        primary = "K011"
    related, prerequisites = [], []
    if primary != "K007" and re.search(r"二次函数|抛物线", text):
        related.append("K007")
        prerequisites.append("K007")
    if primary in {"K004", "K005", "K011", "K013", "K014"} and re.search(r"单调|递增|递减|增函数|减函数", explanation):
        prerequisites.append("K003")
    if primary in {"K006", "K003"} and re.search(r"奇函数|偶函数", explanation):
        related.append("K005")
        prerequisites.append("K005")
    if primary == "K003" and "幂函数" in text:
        related.append("K008")
        prerequisites.append("K008")
    abilities = ["logical_reasoning"]
    methods = ["definition"]
    if re.search(r"参数|实数\s*[a-z]的|[a-z]的取值范围", stem): abilities.append("parameter_analysis")
    if primary in {"K002", "K008", "K009", "K010"}: abilities.append("calculation")
    if primary == "K007": methods = ["substitution"]
    if re.search(r"分类|讨论|分情况", explanation): abilities.append("classification_discussion")
    if primary in {"K003", "K004"}: methods = ["monotonicity"]
    if primary in {"K005", "K006"}: methods = ["definition", "symmetry"]
    if primary == "K013": methods = ["zero_analysis"]
    if "二分" in text: methods.append("bisection")
    if "换元" in text: methods.append("substitution")
    if primary == "K012": abilities.append("graph_analysis"); methods = ["graph_transform"]
    if primary == "K015": abilities.append("modeling"); methods = ["function_model"]
    if primary == "K001": abilities.append("concept_understanding")
    # Explicitly provisional step/integration rubric, never based on chapter number.
    step_count = len(re.findall(r"所以|因此|又|从而|故|首先|其次", explanation))
    difficulty = (4 if "classification_discussion" in abilities else 3
                  if step_count >= 3 or ("parameter_analysis" in abilities and step_count >= 2) else 2)
    if primary == "K001" and step_count <= 1: difficulty = 1
    if primary in {"K009", "K008"} and re.search(r"其中为|下列.*是|判断", stem):
        abilities.append("concept_understanding")
        difficulty = 1
    return primary, related, list(dict.fromkeys(prerequisites)), difficulty, abilities, list(dict.fromkeys(methods))


def extract_questions(path: str | Path, *, max_candidates: int = 12) -> list[CandidateQuestion]:
    """Inspect at most max_candidates choice-question blocks, never insert records."""
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError("max_candidates 必须为正整数")
    path = Path(path)
    blocks = read_docx_blocks(path)
    if not blocks: return []
    section = next((block["text"] for block in blocks if re.match(r"^(?:§\d|必刷小题)", block["text"])), path.stem)
    results = []
    start = 0
    # Each explicit answer closes a potential question. End at next boundary/header.
    answer_positions = [index for index, block in enumerate(blocks)
                        if re.match(r"^答案\s*[:：]?", block["text"])]
    for position_index, answer_index in enumerate(answer_positions):
        answer_block = blocks[answer_index]
        before = blocks[start:answer_index]
        markers = [index for index, block in enumerate(before) if START.match(block["text"])]
        if not markers:
            start = answer_index + 1
            continue
        qstart = start + markers[-1]
        question_blocks = blocks[qstart:answer_index]
        joined = "\n".join(block["text"] for block in question_blocks)
        matches = list(OPTION.finditer(joined))
        raw_answer = re.sub(r"^答案\s*[:：]?\s*", "", answer_block["text"]).strip()
        if not matches and raw_answer not in tuple("ABCD"):
            start = answer_index + 1
            continue
        next_answer = answer_positions[position_index + 1] if position_index + 1 < len(answer_positions) else len(blocks)
        end = answer_index + 1
        explanation_blocks = []
        for index in range(answer_index + 1, next_answer):
            text = blocks[index]["text"]
            if START.match(text) or re.match(r"题型|思维升华|感悟|方法|命题|考试要求|重点解读|课时精练|\[分值|[一二三四五]、.*(?:选择题|填空题|解答题)", text):
                break
            if text.startswith("解析") or explanation_blocks:
                explanation_blocks.append(blocks[index])
                end = index + 1
        stem = joined[:matches[0].start()].strip() if matches else joined.strip()
        options = {}
        for i, match in enumerate(matches):
            key = match.group(1)
            value = joined[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(joined)].strip()
            if key in options: value = "[选项边界待核] " + value
            options[key] = value
        answer_text = re.sub(r"^答案\s*[:：]?\s*", "", answer_block["text"]).strip()
        answer = answer_text if answer_text in tuple("ABCD") else ""
        if "多选" in stem or re.match(r"^[ABCD]{2,4}$", answer_text):
            start = answer_index + 1
            continue
        explanation = "\n".join(block["text"] for block in explanation_blocks)
        explanation = re.sub(r"^解析\s*[:：]?\s*", "", explanation).strip()
        number = START.match(stem)
        label = number.group(0).strip() if number else None
        primary, related, prerequisites, difficulty, abilities, methods = _annotation(stem, explanation, section)
        used = question_blocks + [answer_block] + explanation_blocks
        warnings = list(dict.fromkeys(warning for block in used for warning in block["warnings"]))
        images = list(dict.fromkeys(image for block in used for image in block["images"]))
        status = "image_required" if images or re.search(r"如图|下图|图中|图示|图所示", joined + explanation) else "formula_warning" if warnings else "complete"
        if set(options) != set("ABCD") or not all(options.values()) or not answer or not explanation:
            status = "incomplete"
        source = path.as_posix()
        locator = f"word/document.xml paragraphs {blocks[qstart]['index']}–{blocks[max(answer_index, end-1)]['index']}"
        identifier = "FC-" + hashlib.sha256((source + locator).encode("utf-8")).hexdigest()[:16]
        candidate = CandidateQuestion(identifier, stem, options, answer, explanation, "function_v2", primary,
                                      related, prerequisites, difficulty, abilities, methods, difficulty * 60,
                                      "docx", source, section, label, locator, status,
                                      "reviewed" if status == "complete" else "draft",
                                      ["知识点、难度和预计用时为规则草标，需教师核对；未批准。"], "", 1, warnings, images)
        data = candidate.to_dict()
        candidate.fingerprint = content_fingerprint(data)
        checked = validate_candidate(candidate.to_dict())
        if checked["errors"]:
            candidate.extraction_status = "incomplete"
            candidate.quality_status = "draft"
        elif checked["warnings"] and status == "complete":
            candidate.extraction_status = "manual_review"
            candidate.quality_status = "draft"
        candidate.review_notes.extend(checked["errors"] + checked["warnings"])
        results.append(candidate)
        start = answer_index + 1
        if len(results) >= max_candidates: break
    return results
