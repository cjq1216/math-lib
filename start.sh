#!/bin/sh
set -eu

echo "=== Math Bank - Docker startup ==="

if [ ! -f backend/.env ]; then
    echo "[1/4] Creating backend/.env ..."
    cp backend/.env.example backend/.env
    echo "Configure backend/.env, then run this script again."
    exit 1
fi

echo "[2/4] Building and starting services ..."
docker compose up -d --build

echo "[3/4] Waiting for backend readiness ..."
i=0
while [ "$i" -lt 30 ]; do
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        echo "[4/4] Backend is healthy."
        echo "Frontend: http://localhost:3000"
        echo "API docs: http://localhost:8000/docs"
        echo "Register the first administrator through POST /api/v1/auth/register."
        exit 0
    fi
    i=$((i + 1))
    sleep 2
done

echo "Backend did not become ready."
docker compose logs backend
exit 1
