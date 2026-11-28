FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_USE_MOCK_API=false VITE_API_BASE_URL=""
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --create-home --uid 10001 app \
    && chown app:app /app
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app database/ ./database/
COPY --chown=app:app scripts/start_service.py ./scripts/start_service.py
COPY --chown=app:app scripts/check_deployment.py ./scripts/check_deployment.py
COPY --from=frontend --chown=app:app /frontend/dist/ ./frontend/dist/
USER app
EXPOSE 8000
CMD ["python", "scripts/start_service.py"]
