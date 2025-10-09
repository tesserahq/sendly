#!/bin/bash
set -e

echo "🔧 Running Alembic migrations..."
alembic upgrade head

echo "🚀 Starting Sendly..."

# Start FastAPI application
PORT=${PORT:-8000}
uvicorn app.main:app --host 0.0.0.0 --port $PORT
