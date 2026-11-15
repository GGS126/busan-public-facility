"""규정 파일을 읽어 메모리에 둔다. DB가 정해지면 이 모듈을 교체한다."""

import json
from pathlib import Path

from app.models import RuleData

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_RULES_PATH = DATA_DIR / "sample_rules.json"
HOLIDAYS_PATH = DATA_DIR / "holidays_kr.json"


def load_rule_data(path: Path = SAMPLE_RULES_PATH, holidays_path: Path = HOLIDAYS_PATH) -> RuleData:
    data = json.loads(path.read_text(encoding="utf-8"))
    # 공휴일은 시설과 무관한 공통 자료이므로 모든 시설에 같은 목록을 붙인다.
    calendar = json.loads(holidays_path.read_text(encoding="utf-8"))
    for facility in data["facilities"]:
        facility["holiday_calendar"] = calendar
    return RuleData.model_validate(data)
