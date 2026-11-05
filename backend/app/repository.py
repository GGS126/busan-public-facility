"""규정 파일을 읽어 메모리에 둔다. DB가 정해지면 이 모듈을 교체한다."""

import json
from pathlib import Path

from app.models import FacilityRules

SAMPLE_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_rules.json"


def load_facilities(path: Path = SAMPLE_RULES_PATH) -> dict[str, FacilityRules]:
    data = json.loads(path.read_text(encoding="utf-8"))
    facilities = [FacilityRules.model_validate(item) for item in data["facilities"]]
    return {facility.facility_id: facility for facility in facilities}
