"""규정 파일을 읽어 메모리에 둔다. DB가 정해지면 이 모듈을 교체한다."""

import json
from pathlib import Path

from app.models import RuleData

SAMPLE_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_rules.json"


def load_rule_data(path: Path = SAMPLE_RULES_PATH) -> RuleData:
    return RuleData.model_validate(json.loads(path.read_text(encoding="utf-8")))
