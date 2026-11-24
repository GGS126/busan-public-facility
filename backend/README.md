# 백엔드

요금 규칙 엔진(COMP-06)과 요금 계산·비교 API(API-06)입니다.

서비스는 기본으로 팀 DB(`database/facilities.sqlite3`)의 실제 시설 규정을 읽습니다. 비교·선택지·시설 상세 API가 모두 같은 DB를 씁니다.

`data/sample_rules.json`은 형식 확인용 **가상 데이터**입니다. 실제 시설 규정이 아니므로 시연이나 검증에 사용하지 않습니다. 기존 API 테스트는 이 데이터를 씁니다(`tests/conftest.py`).

`data/holidays_kr.json`은 모든 시설이 함께 쓰는 공휴일 목록입니다. `covered_from`~`covered_to` 밖의 날짜는 공휴일인지 알 수 없는 날로 보고, 공휴일 여부에 따라 요금이 달라지는 시설만 '확인 필요'로 반환합니다. 규정 적용기간이 늘어나거나 임시공휴일이 지정되면 이 파일을 갱신합니다.

## 실행

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

## 테스트

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
