import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.compare import compare_facility
from app.models import CompareRequest, CompareResponse, OptionsResponse
from app.options import build_options
from app.repository import load_rule_data

logger = logging.getLogger(__name__)

app = FastAPI(title="부산 공공시설 이용조건 비교·판정 서비스")
rule_data = load_rule_data()
facilities = {facility.facility_id: facility for facility in rule_data.facilities}


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
        custom = code in ("invalid_time_range", "past_date")
        fields.append(
            {
                "field": ".".join(str(part) for part in error["loc"][1:]),
                "code": code if custom else ("required" if code == "missing" else "invalid_value"),
                "message": error["msg"] if custom else ("필수 항목입니다." if code == "missing" else "값을 확인해 주세요."),
            }
        )
    return error_response(400, "validation_error", "입력값을 확인해 주세요.", fields=fields)


@app.exception_handler(FacilityNotFound)
async def handle_facility_not_found(request: Request, exc: FacilityNotFound) -> JSONResponse:
    return error_response(404, "facility_not_found", "등록되지 않은 시설입니다.")


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # 감면 유형 같은 입력값이 남지 않도록 요청 내용은 기록하지 않는다.
    logger.error("unexpected error: %s %s (%s)", request.method, request.url.path, type(exc).__name__)
    return error_response(500, "internal_error", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


@app.get("/api/options", response_model=OptionsResponse)
def options() -> OptionsResponse:
    return build_options(rule_data)


@app.post("/api/compare", response_model=CompareResponse)
def compare(request: CompareRequest) -> CompareResponse:
    selected = []
    for facility_id in request.facility_ids:
        rules = facilities.get(facility_id)
        if rules is None:
            raise FacilityNotFound
        selected.append(rules)
    return CompareResponse(results=[compare_facility(rules, request.conditions) for rules in selected])
