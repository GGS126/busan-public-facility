import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.compare import compare_facility
from app.models import CompareRequest, CompareResponse, Conditions, OptionsResponse
from app.options import build_options
from app.repository import load_rule_data

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
    check_against_options(request.conditions)
    selected = []
    for facility_id in request.facility_ids:
        rules = facilities.get(facility_id)
        if rules is None:
            raise FacilityNotFound
        selected.append(rules)
    return CompareResponse(results=[compare_facility(rules, request.conditions) for rules in selected])
