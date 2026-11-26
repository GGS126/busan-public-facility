# 부산 공공시설 이용조건 비교·판정 서비스
부산 공공시설의 이용요금과 예약 조건을 비교하고, 사용자 맞춤형 이용 정보를 제공하는 웹 서비스

## 팀 역할

| 팀원 | 담당 |
|---|---|
| 김규성 | AI 기능, DevOps, 프로젝트 관리 |
| 왕연호 | DB, 시설 데이터 |
| 김승일 | 프론트엔드 |
| 배승환 | 백엔드 |

## 팀원 안내

1. [협업 규칙](%ED%98%91%EC%97%85%20%EA%B7%9C%EC%B9%99.md)을 읽습니다.
2. Issues에 작업을 등록하고 담당자를 지정합니다.
3. 최신 `develop`에서 `feature/이름/기능명` 브랜치를 만듭니다.
4. 작업 후 `develop` 대상으로 PR을 열고 다른 팀원의 리뷰를 받습니다.

Issue는 담당자와 할 일을 공유하는 작업 카드이고, PR은 개발한 변경을 리뷰받고 합치는 요청입니다.
사용 예시는 [협업 규칙의 Issue 사용 안내](%ED%98%91%EC%97%85%20%EA%B7%9C%EC%B9%99.md#issue-사용-안내)를 참고하세요.

`develop`은 개발 통합 브랜치, `main`은 검증된 최종 안정 브랜치입니다.

## 실행과 검사

React·Vite 프론트엔드, FastAPI 백엔드, SQLite 시설 규정과 Gemini 조건 추출로 구성됩니다. 현재 테니스장 4곳·축구장 4곳을 비교하며, 직접 예약·결제·실시간 잔여석 확인은 제공하지 않습니다.

**처음 실행할 때는 [공통 실행 및 검사 안내](docs/공통%20실행%20및%20검사%20안내.md)를 따라 주세요.** DB 생성, 백엔드·프론트 실행, 환경변수와 오류 해결 방법을 정리했습니다. Gemini 키 없이도 직접 입력·검색·비교와 자동 검사를 할 수 있습니다.

- 백엔드 검사: 저장소 루트에서 `./.venv/Scripts/python scripts/check_backend.py` (macOS·Linux: `.venv/bin/python scripts/check_backend.py`)
- 프론트 검사: `frontend`에서 `npm ci`, `npm test`, `npm run lint`, `npm run build`
- `develop`·`main` 대상 PR과 두 브랜치 push에서 GitHub Actions `CI`가 같은 검사를 실행합니다. 실제 Gemini 호출은 자동 검사에 포함하지 않습니다.

[최신 개발 현황 및 남은 작업](https://github.com/GGS126/busan-public-facility/issues/29)을 확인해 주세요. [결정 기록](docs/decisions.md)과 [개발 준비 초안](docs/개발%20준비%20및%20논의%20초안.md)은 초기 논의 기록이며 실제 구현에 맞춘 최종 문서 갱신이 필요합니다.
