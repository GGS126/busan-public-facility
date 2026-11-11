"""Normalize natural-language search conditions for API-01. The caller supplies the extraction function."""

import re
import unicodedata
from collections.abc import Callable, Mapping
from datetime import date

from pydantic import TypeAdapter, ValidationError

from app.models import BandTime, ClockTime

QUESTIONS = {
    "sport": "어떤 종목을 이용하시나요?",
    "districts": "어느 지역에서 찾으시나요?",
    "date": "어느 날짜에 이용하시나요?",
    "start_time": "몇 시에 시작하시나요?",
    "end_time": "몇 시에 끝나나요?",
    "headcount": "이용 인원을 1명 이상으로 알려 주세요.",
    "discount_types": "적용할 감면 유형이 있는지 확인해 주세요.",
}
REQUIRED_FIELDS = ("sport", "districts", "date", "start_time", "end_time")
DATE_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
START_TIME = TypeAdapter(ClockTime)
END_TIME = TypeAdapter(BandTime)
SENSITIVE_PATTERN = re.compile(
    r"(?<!\d)(?:\d{6}[-.\s]?\d{7}|(?:\+82[-.\s]?|0)1[016789][- .]?\d{3,4}[- .]?\d{4})(?!\d)"
    r"|(?<!\d)(?:0(?:2|[3-6][1-5])|\+82[- .]?(?:2|[3-6][1-5]))[- .]?\d{3,4}[- .]?\d{4}(?!\d)"
    r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
)


def parse_query(
    query: str,
    *,
    today: date,
    extract: Callable[[str, date], Mapping[str, object]],
) -> dict:
    """Normalize extracted fields; `ok` still requires user confirmation in the UI."""
    query = unicodedata.normalize("NFKC", query).strip()
    if len(query) > 500:
        return {**_result("llm_failed", {}), "message": "이용 조건은 500자 이내로 입력해 주세요."}
    if not query:
        return _result("need_more", {}, list(REQUIRED_FIELDS))
    if SENSITIVE_PATTERN.search(query):
        return {**_result("llm_failed", {}), "message": "개인정보를 빼고 다시 입력하거나 직접 입력해 주세요."}

    try:
        raw = extract(query, today)
    except Exception:
        # Provider exceptions can contain request text or credentials.
        return _result("llm_failed", {})

    if not isinstance(raw, Mapping):
        return _result("llm_failed", {})

    conditions = {"source": "llm"}
    missing = []
    for field in REQUIRED_FIELDS:
        value = raw.get(field)
        if not _valid(field, value, today):
            missing.append(field)
            continue
        conditions[field] = _clean(value)

    for field in ("headcount", "discount_types"):
        value = raw.get(field)
        if field == "headcount" and value is None:
            continue
        if not _valid(field, value, today):
            missing.append(field)
            continue
        conditions[field] = _clean(value)

    start = conditions.get("start_time")
    end = conditions.get("end_time")
    if start and end and end <= start:
        conditions.pop("end_time")
        missing.append("end_time")
        result = _result("need_more", conditions, missing)
        result["questions"]["end_time"] = "시작 시간보다 늦은 종료 시간을 알려 주세요."
        return result

    return _result("need_more" if missing else "ok", conditions, missing)


def _valid(field: str, value: object, today: date) -> bool:
    if field == "sport":
        return isinstance(value, str) and bool(value.strip())
    if field in {"districts", "discount_types"}:
        return (
            isinstance(value, list)
            and (field == "discount_types" or bool(value))
            and all(isinstance(item, str) and item.strip() for item in value)
        )
    if field == "headcount":
        return type(value) is int and value > 0
    if field in {"start_time", "end_time"}:
        try:
            (END_TIME if field == "end_time" else START_TIME).validate_python(value, strict=True)
            return True
        except ValidationError:
            return False
    if not isinstance(value, str) or not DATE_FORMAT.fullmatch(value):
        return False
    try:
        return date.fromisoformat(value) >= today
    except ValueError:
        return False


def _clean(value: object) -> object:
    if isinstance(value, list):
        return list(dict.fromkeys(item.strip() for item in value))
    return value.strip() if isinstance(value, str) else value


def _result(status: str, conditions: dict, missing: tuple | list = ()) -> dict:
    return {
        "status": status,
        "conditions": conditions,
        "missing_fields": list(missing),
        "questions": {field: QUESTIONS[field] for field in missing},
    }
