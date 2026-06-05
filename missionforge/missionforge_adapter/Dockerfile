# MissionForge Adapter — Dockerfile
#
# Build context must be the missionforge/ root directory so that both
# missionforge_adapter/ and semantic_overlay/ are accessible.
# This is done by docker-compose.yml: context: .

FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY missionforge_adapter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy FastAPI application
COPY missionforge_adapter/app/ ./app/

# Copy semantic overlay alongside app so imports work
COPY semantic_overlay/ ./semantic_overlay/

# Expose FastAPI port
EXPOSE 8000

# PYTHONPATH makes both /app/app and /app/semantic_overlay importable
ENV PYTHONPATH=/app/app:/app/semantic_overlay

# Run uvicorn pointing at the app/ package
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/app"]
