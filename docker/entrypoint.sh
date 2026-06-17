#!/bin/sh
set -e

echo "Starting LifeOps Goals Service..."
echo "Environment: ${ENVIRONMENT:-development}"
echo "Port: ${PORT:-8002}"

exec uvicorn app.main:app \
    --host "${SERVICE_HOST:-0.0.0.0}" \
    --port "${PORT:-8002}" \
    --workers 1 \
    --loop uvloop \
    --http httptools \
    --log-level "${LOG_LEVEL:-info}" \
    --no-access-log
