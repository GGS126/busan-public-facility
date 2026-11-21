# 백엔드

요금 규칙 엔진(COMP-06)과 요금 계산·비교 API(API-06)입니다.

`data/sample_rules.json`은 형식 확인용 **가상 데이터**입니다. 실제 시설 규정이 아니므로 시연이나 검증에 사용하지 않습니다.

## 실행

Python 3.13에서 확인했습니다. 아래 명령은 `backend` 폴더에서 실행합니다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS·Linux는 .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:app --reload
```

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
자연어 입력이 원문 또는 정규화 후 500자를 넘으면 `llm_failed`로 안내합니다.
추출 날짜가 한국 시간 기준 오늘부터 365일을 넘으면 날짜를 다시 확인합니다. 실제 예약 가능 기간은 시설 규정에 따릅니다.
Gemini 요청은 재시도를 포함해 총 30초로 제한합니다.
지역을 지정하지 않으면 `districts: []`로 부산 전체를 뜻합니다. 감면 유형이 불명확하면 `need_more`로 확인을 요청합니다.
Gemini 호출은 서버 프로세스마다 최근 60초 동안 15회(재시도 포함), 동시 4회로 제한합니다. 제한에 도달하면 직접 입력을 안내합니다.
자연어 추출 결과를 공통 입력 검증에 연결하는 작업은 후속으로 진행합니다.

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
| `app/repository.py` | 규정 파일 읽기. DB가 정해지면 교체 |
| `app/main.py` | API 경로와 공통 오류 응답 |

Gemini 추출 요청은 재시도를 포함해 총 30초의 제한을 사용합니다. JSON 형식 오류와 일시 HTTP 오류(429·500·502·503·504), 시간 초과·연결 오류는 한 번 더 시도하며 각 시도는 호출 한도에 포함됩니다.
