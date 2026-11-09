# 백엔드

요금 규칙 엔진(COMP-06)과 요금 계산·비교 API(API-06)입니다.

`data/sample_rules.json`은 형식 확인용 **가상 데이터**입니다. 실제 시설 규정이 아니므로 시연이나 검증에 사용하지 않습니다.

`data/holidays_kr.json`은 모든 시설이 함께 쓰는 공휴일 목록입니다. `covered_from`~`covered_to` 밖의 날짜는 공휴일인지 알 수 없는 날로 보고, 공휴일 여부에 따라 요금이 달라지는 시설만 '확인 필요'로 반환합니다. 규정 적용기간이 늘어나거나 임시공휴일이 지정되면 이 파일을 갱신합니다.

## 실행

Python 3.13에서 확인했습니다. 아래 명령은 `backend` 폴더에서 실행합니다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS·Linux는 .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:app --reload
```

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
| `app/compare.py` | 요금 결과에 예약·취소 조건, 증빙서류, 출처를 묶음 |
| `app/options.py` | 직접 입력 화면의 종목·지역·감면 유형 선택지 |
| `app/repository.py` | 규정 파일과 공휴일 목록 읽기. DB가 정해지면 교체 |
| `app/main.py` | API 경로와 공통 오류 응답 |
