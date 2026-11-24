import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.compare import compare_facility
from app.detail import facility_detail
from app.models import (
    KST, CompareRequest, CompareResponse, Conditions, FacilityDetail, FacilityRules, IsoDate, OptionsResponse, RuleData,
)
from app.options import build_options
from app.repository import SQLITE_PATH, load_rule_data, load_sqlite_rule_data

logger = logging.getLogger(__name__)


def load_service_data(source: str | None = None, sqlite_path: Path = SQLITE_PATH) -> RuleData:
    """서비스가 쓸 규정. 기본은 팀 DB(SQLite)이고, RULE_DATA_SOURCE=sample이면 가상 데이터를 쓴다.

    DB가 없을 때 가상 데이터로 몰래 바꾸면 실제 시설 요금처럼 보이므로, 시작하지 않고 생성 방법을 알린다.
    DB를 다시 생성하면 서버를 재시작해야 반영된다.
    """
    source = source if source is not None else os.getenv("RULE_DATA_SOURCE", "sqlite").strip() or "sqlite"
    if source == "sample":
        return load_rule_data()
    if source != "sqlite":
        raise RuntimeError(f"RULE_DATA_SOURCE는 sqlite 또는 sample이어야 합니다: {source}")
    if not sqlite_path.is_file():
        raise RuntimeError(
            f"규정 DB가 없습니다: {sqlite_path}. 'python database/build_db.py'로 생성하거나, "
            "가상 데이터로 실행하려면 RULE_DATA_SOURCE=sample을 설정하세요."
        )
    return load_sqlite_rule_data(sqlite_path)


app = FastAPI(title="부산 공공시설 이용조건 비교·판정 서비스")
rule_data = load_service_data()
facilities = {facility.facility_id: facility for facility in rule_data.facilities}
available_options = build_options(rule_data)

HTTP_ERRORS = {
    404: ("not_found", "요청한 경로를 찾을 수 없습니다."),
    405: ("method_not_allowed", "지원하지 않는 요청 방식입니다."),
}


class FacilityNotFound(Exception):
    pass


def error_response(status_code: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, **extra}})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # 입력값이 그대로 돌아가지 않도록 항목 위치와 사유만 반환한다.
    fields = []
    for error in exc.errors():
        code = error["type"]
        custom = code in ("invalid_time_range", "past_date", "invalid_option", "invalid_discount", "invalid_lighting_minutes")
        # JSON 형식 오류의 위치는 항목이 아니라 문자 위치이므로 요청 본문 전체의 오류로 표시한다.
        location = [] if code == "json_invalid" else error["loc"][1:]
        fields.append(
            {
                "field": ".".join(str(part) for part in location) or "body",
                "code": code if custom else ("required" if code == "missing" else "invalid_value"),
                # 날짜 형식 오류는 코드는 invalid_value로 두고 YYYY-MM-DD 안내 문구를 그대로 전한다.
                "message": error["msg"] if custom or code == "date_format" else ("필수 항목입니다." if code == "missing" else "값을 확인해 주세요."),
            }
        )
    return error_response(400, "validation_error", "입력값을 확인해 주세요.", fields=fields)


@app.exception_handler(FacilityNotFound)
async def handle_facility_not_found(request: Request, exc: FacilityNotFound) -> JSONResponse:
    return error_response(404, "facility_not_found", "등록되지 않은 시설입니다.")


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    code, message = HTTP_ERRORS.get(exc.status_code, ("http_error", "요청을 처리할 수 없습니다."))
    response = error_response(exc.status_code, code, message)
    # 405의 Allow처럼 프레임워크가 정한 헤더는 유지한다.
    response.headers.update(exc.headers or {})
    return response


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # 감면 유형 같은 입력값이 남지 않도록 요청 내용은 기록하지 않는다.
    logger.error("unexpected error: %s %s (%s)", request.method, request.url.path, type(exc).__name__)
    return error_response(500, "internal_error", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


@app.get("/api/options", response_model=OptionsResponse)
def options() -> OptionsResponse:
    return available_options


def check_against_options(conditions: Conditions) -> None:
    """선택지에 없는 값은 입력 오류로 돌려보낸다. 시설에만 없는 값은 규칙 엔진이 확인 필요로 처리한다."""
    errors = []
    if conditions.sport not in {option.code for option in available_options.sports}:
        errors.append(
            {"type": "invalid_option", "loc": ("body", "conditions", "sport"), "msg": "선택할 수 없는 종목입니다."}
        )
    discount_codes = {option.code for option in available_options.discount_types}
    if not set(conditions.discount_types) <= discount_codes:
        errors.append(
            {
                "type": "invalid_option",
                "loc": ("body", "conditions", "discount_types"),
                "msg": "선택할 수 없는 감면 유형입니다.",
            }
        )
    for index, discount in enumerate(conditions.discounts):
        if discount.type not in discount_codes:
            errors.append(
                {
                    "type": "invalid_option",
                    "loc": ("body", "conditions", "discounts", index, "type"),
                    "msg": "선택할 수 없는 감면 유형입니다.",
                }
            )
    if errors:
        raise RequestValidationError(errors)


@app.post("/api/compare", response_model=CompareResponse)
def compare(request: CompareRequest) -> CompareResponse:
    check_against_options(request.conditions)
    selected = []
    for facility_id in request.facility_ids:
        rules = facilities.get(facility_id)
        if rules is None:
            raise FacilityNotFound
        selected.append(rules)
    return CompareResponse(results=[compare_facility(rules, request.conditions) for rules in selected])


def known_facility(facility_id: str) -> FacilityRules:
    # 의존성은 엔드포인트의 쿼리 검증보다 먼저 실행되므로, 없는 시설이면 날짜 형식과 관계없이 404다.
    rules = facilities.get(facility_id)
    if rules is None:
        raise FacilityNotFound
    return rules


# 경로 매개변수라서 /api/facilities/options 같은 고정 경로보다 뒤에 둔다.
@app.get("/api/facilities/{facility_id}", response_model=FacilityDetail)
def facility(
    rules: FacilityRules = Depends(known_facility), day: IsoDate | None = Query(default=None, alias="date")
) -> FacilityDetail:
    today = datetime.now(KST).date()
    if day is not None and day < today:
        raise RequestValidationError(
            [{"type": "past_date", "loc": ("query", "date"), "msg": "지난 날짜는 선택할 수 없습니다."}]
        )
    return facility_detail(rules, day or today)
