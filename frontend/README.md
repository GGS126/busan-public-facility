# 프론트엔드

React·JavaScript·Vite 기반 조건 입력·시설 검색·요금 비교 화면입니다.
처음 설치할 때는 [공통 실행 및 검사 안내](../docs/공통%20실행%20및%20검사%20안내.md)를 참고하세요.

Node.js 24와 npm을 설치한 뒤 `frontend`에서 실행합니다.

```bash
npm ci
npm run dev -- --host 127.0.0.1
```

터미널에 출력된 주소를 엽니다. 백엔드는 별도 터미널에서 `127.0.0.1:8000`으로 실행합니다. Vite 개발 서버가 `/api` 요청을 백엔드로 전달합니다.

## 설정

기본은 실제 API입니다. 별도 설정이 필요하면 `.env.example`을 `.env.local`로 복사합니다. 기존 파일은 덮어쓰지 않습니다.

| 환경변수 | 기본 | 용도 |
|---|---|---|
| `VITE_USE_MOCK_API` | `false` | `true`일 때만 개발용 모의 API 사용. 실제 계산 검증에 사용하지 않음 |
| `VITE_API_BASE_URL` | 빈 값 | `/api` 상대 경로 사용. 배포 시 필요한 API 주소를 지정하거나 같은 도메인 프록시 구성 |

`VITE_` 값은 클라이언트에 포함되므로 API 키를 넣지 않습니다. Gemini 키는 백엔드에만 설정합니다. 환경변수 변경 후 Vite를 재시작합니다.

## 검사

```bash
npm test
npm run lint
npm run build
```

테스트는 조건·시설·시간 변경 후 이전 비교 응답과 오류가 새 화면을 덮어쓰지 않는지, 감면 입력 전달 등을 확인합니다. GitHub Actions도 같은 명령을 실행합니다.

`npm run build`는 정적 파일 생성 검사이고 `npm run preview`는 빌드 결과를 로컬 확인합니다. preview도 현재 `/api` 프록시를 이어받으므로 백엔드를 함께 실행합니다. 실제 호스팅에서는 프록시·HTTPS를 별도로 구성합니다. [Vite preview 설정](https://vite.dev/config/preview-options#preview-proxy)을 참고하세요.
