import logging
import os
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.compare import compare_facility
from app.facility_catalog import DB_PATH, read_catalog, read_fixed_slots
from app.gemini_extractor import GeminiExtractor, GeminiHTTPError, GeminiResponseError
from app.models import (
    KST,
    CompareRequest,
    CompareResponse,
    Conditions,
    FacilitySearchRequest,
    OptionsResponse,
    QueryParseRequest,
    QueryParseResponse,
)
from app.options import build_options
from app.query_parser import parse_query
from app.repository import load_rule_data
from app.sqlite_compare import compare_sqlite

logger = logging.getLogger(__name__)

app = FastAPI(title="부산 공공시설 이용조건 비교·판정 서비스")
rule_data = load_rule_data()
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
        custom = code in ("invalid_time_range", "past_date", "invalid_option")
        # JSON 형식 오류의 위치는 항목이 아니라 문자 위치이므로 요청 본문 전체의 오류로 표시한다.
        location = [] if code == "json_invalid" else error["loc"][1:]
        fields.append(
            {
                "field": ".".join(str(part) for part in location) or "body",
                "code": code if custom else ("required" if code == "missing" else "invalid_value"),
                "message": error["msg"] if custom else ("필수 항목입니다." if code == "missing" else "값을 확인해 주세요."),
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


@app.get("/api/facilities/options", response_model=OptionsResponse)
def facility_search_options():
    if not DB_PATH.is_file():
        return error_response(503, "facility_catalog_unavailable", "시설 데이터를 불러올 수 없습니다.")
    return read_catalog(DB_PATH)[1]


@app.post("/api/facilities/search")
def search_facilities(request: FacilitySearchRequest):
    if not DB_PATH.is_file():
        return error_response(503, "facility_catalog_unavailable", "시설 데이터를 불러올 수 없습니다.")
    conditions = request.conditions
    catalog_facilities, _ = read_catalog(DB_PATH)
    candidates = [facility for facility in catalog_facilities if facility["sport"] == conditions.sport]
    if not candidates:
        return error_response(400, "invalid_option", "선택할 수 없는 종목입니다.")

    fixed_slots = read_fixed_slots(DB_PATH, conditions.date.isoformat())
    results = []
    for facility in candidates:
        if conditions.districts and facility["district"] not in conditions.districts:
            continue
        slots = fixed_slots.get(facility["facility_id"])
        time_status = "unknown"
        if slots and conditions.start_time:
            selected = {"start_time": conditions.start_time, "end_time": conditions.end_time}
            time_status = "eligible" if selected in slots else "not_eligible"
        results.append({
            **facility,
            "time_options": {"selection": "fixed_slot", "slots": slots} if slots else None,
            "time_check": {"status": time_status},
        })
    order = {"eligible": 0, "unknown": 1, "not_eligible": 2}
    results.sort(key=lambda facility: order[facility["time_check"]["status"]])
    alternatives = None
    if not results and conditions.districts:
        alternatives = {"districts": sorted({facility["district"] for facility in candidates})}
    return {"results": results, "alternatives": alternatives}


@app.post("/api/query/parse", response_model=QueryParseResponse, response_model_exclude_unset=True)
def parse_natural_language(request: QueryParseRequest) -> dict:
    catalog = read_catalog(DB_PATH)[1] if DB_PATH.is_file() else available_options
    return parse_with_options(request, catalog)


def parse_with_options(request: QueryParseRequest, catalog: OptionsResponse) -> dict:
    def extract(query, today):
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            logger.warning("Gemini extraction failed: code=missing_api_key")
            return None
        try:
            provider = GeminiExtractor(
                key,
                sport_codes={option.code: option.label for option in catalog.sports},
                discount_codes={option.code: option.label for option in catalog.discount_types},
                districts=catalog.districts,
                model=os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite",
            )
        except GeminiResponseError as error:
            logger.warning("Gemini extraction failed: type=%s code=%s", type(error).__name__, error.code)
            return None

        for attempt in (1, 2):
            try:
                return provider(query, today)
            except GeminiResponseError as error:
                logger.warning("Gemini extraction failed: type=%s code=%s attempt=%d",
                               type(error).__name__, error.code, attempt)
                if error.code not in {"invalid_output_json", "invalid_api_json", "unexpected_extraction_fields"}:
                    break
            except GeminiHTTPError as error:
                logger.warning("Gemini extraction failed: type=%s status=%d", type(error).__name__, error.status)
                break
            except Exception as error:
                # Exception messages may include request text or credentials.
                logger.warning("Gemini extraction failed: type=%s", type(error).__name__)
                break
        return None

    result = parse_query(request.query, today=datetime.now(KST).date(), extract=extract)
    if result["status"] == "llm_failed":
        result.setdefault("message", "조건을 추출하지 못했습니다. 직접 입력해 주세요.")
    return result


def check_against_options(conditions: Conditions) -> None:
    """선택지에 없는 값은 입력 오류로 돌려보낸다. 시설에만 없는 값은 규칙 엔진이 확인 필요로 처리한다."""
    errors = []
    if conditions.sport not in {option.code for option in available_options.sports}:
        errors.append(
            {"type": "invalid_option", "loc": ("body", "conditions", "sport"), "msg": "선택할 수 없는 종목입니다."}
        )
    if not set(conditions.discount_types) <= {option.code for option in available_options.discount_types}:
        errors.append(
            {
                "type": "invalid_option",
                "loc": ("body", "conditions", "discount_types"),
                "msg": "선택할 수 없는 감면 유형입니다.",
            }
        )
    if errors:
        raise RequestValidationError(errors)


@app.post("/api/compare", response_model=CompareResponse)
def compare(request: CompareRequest) -> CompareResponse:
    has_sqlite = DB_PATH.is_file()
    if not has_sqlite or any(facility_id in facilities for facility_id in request.facility_ids):
        check_against_options(request.conditions)
    results = []
    for facility_id in request.facility_ids:
        rules = facilities.get(facility_id)
        if rules is not None:
            results.append(compare_facility(rules, request.conditions))
            continue
        result = compare_sqlite(DB_PATH, facility_id, request.conditions) if has_sqlite else None
        if result is None:
            raise FacilityNotFound
        results.append(result)
    return CompareResponse(results=results)
