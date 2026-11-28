# 백엔드

요금 규칙 엔진(COMP-06)과 요금 계산·비교 API(API-06)입니다.

서비스는 기본으로 팀 DB(`database/facilities.sqlite3`)의 실제 시설 규정을 읽습니다. 비교·선택지·시설 상세 API가 모두 같은 DB를 씁니다.

`data/sample_rules.json`은 형식 확인용 **가상 데이터**입니다. 실제 시설 규정이 아니므로 시연이나 검증에 사용하지 않습니다. 기존 API 테스트는 이 데이터를 씁니다(`tests/conftest.py`).

`data/holidays_kr.json`은 모든 시설이 함께 쓰는 공휴일 목록입니다. `covered_from`~`covered_to` 밖의 날짜는 공휴일인지 알 수 없는 날로 보고, 공휴일 여부에 따라 요금이 달라지는 시설만 '확인 필요'로 반환합니다. 규정 적용기간이 늘어나거나 임시공휴일이 지정되면 이 파일을 갱신합니다.

## 실행

처음 설치·실행하거나 Windows에서 가상환경 경로가 헷갈리면 [공통 실행 및 검사 안내](../docs/공통%20실행%20및%20검사%20안내.md)를 참고하세요. 저장소 루트의 `.venv`를 사용하는 통일된 절차와 `.env.example`을 제공합니다. 이 문서의 `backend/.venv` 방식과는 Python 실행 경로만 다르므로 한 가지 방식을 선택해 사용합니다.

Python 3.13에서 확인했습니다. 아래 명령은 `backend` 폴더에서 실행합니다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS·Linux는 .venv/bin/python
.venv/Scripts/python ../database/build_db.py               # 규정 DB 생성. JSON을 고치면 다시 실행
.venv/Scripts/python -m uvicorn app.main:app --reload
```

DB가 없으면 서버가 시작되지 않고 생성 방법을 알려 줍니다. 가상 데이터와 달리 실제 요금처럼 보이면 안 되므로 가상 데이터로 대신 실행하지 않습니다. DB를 다시 생성하면 서버를 재시작해야 반영됩니다.

| 환경변수 | 값 | 설명 |
|---|---|---|
| `RULE_DATA_SOURCE` | `sqlite`(기본), `sample` | `sample`이면 가상 데이터로 실행합니다. 화면 개발처럼 DB 없이 확인할 때만 씁니다. |

API 문서는 서버 실행 후 `http://127.0.0.1:8000/docs`에서 확인합니다.

## 자연어 조건 추출

서버를 시작하기 전에 서버 프로세스의 `GEMINI_API_KEY` 환경변수를 설정합니다.
PowerShell에서는 아래 명령을 실행한 뒤 키를 입력하면 Python이 실행한 서버에만 키가 전달됩니다.

```powershell
.venv/Scripts/python -c "import getpass, os, runpy, sys; os.environ['GEMINI_API_KEY'] = getpass.getpass('Gemini API key: '); sys.argv = ['uvicorn', 'app.main:app']; runpy.run_module('uvicorn', run_name='__main__')"
```

`POST /api/query/parse`에 `{"query":"내일 해운대구에서 저녁 7시부터 9시까지 풋살 하고 싶어요"}`처럼 보냅니다.
응답은 `status`, `conditions`, `missing_fields`, `questions`를 포함합니다.
`ok`는 사용자가 확인할 추출 결과이고, `need_more`는 빠진 조건과 질문을 담습니다.
`llm_failed`이면 직접 입력으로 이어갑니다. 키는 서버에만 설정합니다.
모델은 `GEMINI_MODEL`로 지정할 수 있으며 기본값은 `gemini-3.5-flash-lite`입니다.
Gemini 3 계열은 `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3-flash-preview`, `gemini-3.1-pro-preview`를 지원합니다.
자연어 입력이 원문 500자를 넘으면 `llm_failed`로 안내합니다.
추출 날짜가 한국 시간 기준 오늘부터 365일을 넘으면 날짜를 다시 확인합니다. 실제 예약 가능 기간은 시설 규정에 따릅니다.
Gemini 요청은 재시도를 포함해 총 30초로 제한합니다.
지역을 지정하지 않으면 `districts: []`로 부산 전체를 뜻합니다. 감면 유형이 불명확하면 `need_more`로 확인을 요청합니다.
Gemini 호출은 서버 프로세스마다 최근 60초 동안 15회(재시도 포함), 동시 4회로 제한합니다. 제한에 도달하면 직접 입력을 안내합니다.
자연어 추출 결과를 공통 입력 검증에 연결하는 작업은 후속으로 진행합니다.

## SQLite 시설 검색

`GET /api/facilities/options`와 `POST /api/facilities/search`는 저장소의 `database/facilities.sqlite3`를 읽습니다.
먼저 저장소 루트에서 `python database/build_db.py`를 실행해 SQLite를 생성합니다.
검색 요청은 `{"conditions":{"sport":"tennis","districts":[],"date":"2026-11-30","source":"direct"}}` 형태입니다.
지역 목록을 비우면 부산 전체를 검색합니다. 시작·종료 시간을 함께 보내면 고정 회차와 대조합니다.
SQLite가 있으면 자연어 추출도 같은 종목·지역·감면 선택지를 사용합니다.
실제 시설의 `POST /api/compare`는 SQLite 규정을 공통 규칙 엔진으로 계산합니다. 기본요금·필수/선택 조명·감면과 공휴일을 규정에 따라 처리하며, 필요한 규정이 없거나 충돌하면 합계를 확정하지 않습니다.
`/api/options`와 `/api/facilities/options`는 같은 서비스 선택지를 반환합니다. 가상 데이터는 `RULE_DATA_SOURCE=sample`로 명시한 경우에만 사용합니다. 시설 검색은 SQLite를 조회하므로 실제 전체 흐름 검증에는 `sqlite` 모드를 사용합니다.
백엔드 없이 화면을 확인할 때는 프론트 환경변수 `VITE_USE_MOCK_API=true`를 설정하고 직접 입력을 사용합니다.

## 테스트

CI와 동일한 DB 생성·감사·백엔드 테스트 전체를 실행하려면 저장소 루트에서 다음을 실행합니다. Gemini 키나 별도 서버 실행은 필요하지 않습니다.

```powershell
./.venv/Scripts/python scripts/check_backend.py
```

`database/test_*.py`가 있으면 추가 DB 테스트도 함께 검사합니다. 백엔드 테스트만 실행할 때는 이 문서의 `backend` 가상환경 기준으로 아래 명령을 사용합니다.

```bash
.venv/Scripts/python -m pytest
```

## 구조

| 파일 | 역할 |
|---|---|
| `app/models.py` | 규정 데이터와 요청·응답 형식, 입력 검증 |
| `app/engine.py` | 규칙 엔진. FastAPI·DB·LLM에 의존하지 않는 순수 함수 |
| `app/compare.py` | 정기 휴장일을 먼저 판정하고, 요금 결과에 예약·취소 조건, 증빙서류, 출처를 묶음 |
| `app/options.py` | 직접 입력 화면의 종목·지역·감면 유형 선택지 |
| `app/repository.py` | 팀 DB(SQLite)·가상 데이터와 공휴일 목록을 규칙 엔진 형식으로 읽기 |
| `app/main.py` | API 경로와 공통 오류 응답 |

Gemini 추출 요청은 재시도를 포함해 총 30초의 제한을 사용합니다. JSON 형식 오류와 일시 HTTP 오류(500·502·503·504), 시간 초과·연결 오류는 한 번 더 시도하며 각 시도는 호출 한도에 포함됩니다.

시설 검색·선택지와 SQLite 비교·휴장 판정을 이 브랜치에서 함께 연결합니다.
로컬 실행 전 저장소 루트에서 `python database/build_db.py`로 DB를 생성합니다.
감면 계산을 확인할 수 없는 경우에는 합계를 확정하지 않고 확인 필요로 표시합니다.
SQLite 요금은 `load_sqlite_rule_data()` → `compare_facility()`의 공통 규칙 엔진으로 계산합니다. `query_api.quote()`는 API 계산 경로에서 사용하지 않습니다. 휴장·규정 충돌 판정은 비교 서비스에서 먼저 확인합니다.

HTTP 429는 즉시 재시도하지 않습니다. DNS 조회를 포함한 대기시간이 만료되면 직접 입력으로 전환할 수 있으며, 아직 종료되지 않은 연결 작업도 최대 4개로 제한합니다.

SQLite 비교는 정기 휴장 여부를 먼저 확인합니다. `payment_due`는 확정된 온라인 선결제액이며, `online_prepay`·`onsite_payment`·`payment_unverified`로 확인된 결제 구분을 제공합니다. 결제 방식이 미확인인 옵션은 `payment_unverified`로 구분하고 `payment_due`는 비웁니다. 요금 자체가 확인된 경우 총요금과 확인된 선결제액은 공통 엔진의 결과대로 제공합니다.

시설 검색은 시설 목록·시간 정책·회차·휴장 정보를 하나의 읽기 전용 DB 스냅샷에서 조회합니다. 적용 기간이 겹치는 규정은 `slot_status: rule_conflict`로 반환하며, 화면에서 충돌 안내와 함께 비교 대상 선택을 차단합니다.

자연어 지역은 부산 16개 구·군을 공통 기준으로 검증합니다. 해당 지역에 시설이 없으면 검색 결과 없음과 대체 지역을 안내합니다. 입력은 원문과 정규화 후 문자열 모두 500자 이하여야 합니다.

#23은 #30의 `load_service_data()`와 `compare_facility()`를 사용합니다. 별도 SQLite 비교 어댑터는 제거했습니다. `/api/options`와 `/api/facilities/options`는 같은 선택지를 반환하며, 고정 검색 경로는 시설 상세 경로보다 앞에 선언합니다. DB를 다시 생성하면 백엔드를 재시작해 주세요.
