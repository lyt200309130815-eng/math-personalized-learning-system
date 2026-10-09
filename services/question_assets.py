"""Validate diagram references and separate pre-answer/solution display roles."""
import logging
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def asset_path(asset):
    path = (ROOT / asset['path']).resolve()
    if (ROOT / 'data/question_assets/images/geometry').resolve() not in path.parents:
        raise ValueError('题图路径超出正式资产目录')
    return path


def readable_asset(asset):
    try:
        with Image.open(asset_path(asset)) as image:
            image.verify()
        return True
    except (OSError, ValueError, KeyError):
        return False


def visible_assets(question, *, solution=False):
    roles = {'solution_diagram'} if solution else {'question_diagram', 'option_image'}
    return [a for a in question.get('diagram_assets', []) if a['role'] in roles]


def diagrams_available(question):
    if not question.get('diagram_required'):
        return True
    assets = visible_assets(question)
    valid = bool(assets) and all(readable_asset(a) for a in assets)
    if not valid:
        logging.getLogger(__name__).warning('Skipping geometry question with missing required diagram: %s', question.get('id'))
    return valid


def geometry_trainable(question, *, check_files=True):
    valid = (question.get('real_question') is True and question.get('quality_status') == 'approved'
             and question.get('formula_status') == 'valid' and question.get('answer_leak_status') == 'clean'
             and question.get('structure_status') == 'valid')
    # Historical approved records predate the explicit production-gate fields.
    # When present, manual approval alone never overrides a blocked gate.
    if question.get('review_status', 'approved') != 'approved' or question.get('production_gate_status', 'valid') != 'valid':
        valid = False
    if 'difficulty' in question and (type(question['difficulty']) is not int or not 1 <= question['difficulty'] <= 5):
        valid = False
    if question.get('diagram_required') and not visible_assets(question):
        valid = False
    return valid and (not check_files or diagrams_available(question))
