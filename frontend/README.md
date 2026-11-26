# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

기본 실행은 실제 API를 사용합니다. 백엔드 없이 화면을 확인할 때는 `VITE_USE_MOCK_API=true`를 설정하세요. 실제 API로 정적 배포할 때는 `VITE_API_BASE_URL`을 설정하거나 배포 환경에서 `/api`를 백엔드로 연결하세요.

## 비교 요청 회귀 검사

`npm test`로 조건·시설·시간 변경 후 이전 비교 응답과 오류가 새 화면을 덮어쓰지 않는지 확인합니다.
