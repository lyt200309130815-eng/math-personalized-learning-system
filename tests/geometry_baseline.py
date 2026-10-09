"""Historical V1.1C/V1.1D assertions run against the preserved pre-V1.1E backup."""
import json
from services.geometry_review import ROOT

def historical_database():
    result = ROOT/'data/question_bank/geometry_v1_1e/migration_result.json'
    if result.exists():
        return json.loads(result.read_text(encoding='utf-8'))['backup']
    return ROOT/'math_ai.db'
