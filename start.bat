@echo off
setlocal

echo === Math Bank - Docker startup ===

if not exist backend\.env (
    echo [1/4] Creating backend\.env ...
    copy backend\.env.example backend\.env > nul
    echo Configure backend\.env, then run this script again.
    exit /b 1
)

echo [2/4] Building and starting services ...
docker compose up -d --build
if errorlevel 1 exit /b 1

echo [3/4] Waiting for backend readiness ...
for /l %%i in (1,1,30) do (
    curl -fsS http://localhost:8000/health > nul 2>&1 && goto healthy
    timeout /t 2 /nobreak > nul
)

echo Backend did not become ready.
docker compose logs backend
exit /b 1

:healthy
echo [4/4] Backend is healthy.
echo Frontend: http://localhost:3000
echo API docs: http://localhost:8000/docs
echo Register the first administrator through POST /api/v1/auth/register.
endlocal
