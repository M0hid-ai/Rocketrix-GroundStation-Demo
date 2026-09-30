# One container: builds the dashboard, then FastAPI serves it plus the API and WebSocket.
FROM node:20-alpine AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 GS_DATA_DIR=/data PORT=8000
WORKDIR /app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=ui /app/frontend/dist frontend/dist
WORKDIR /app/backend
EXPOSE 8000
# --proxy-headers: trust the host's HTTPS proxy so session cookies are marked Secure
CMD uvicorn groundstation.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
