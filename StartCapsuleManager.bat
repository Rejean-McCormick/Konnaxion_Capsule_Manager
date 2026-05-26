@echo off
setlocal

REM ============================================================
REM Konnaxion Capsule Manager - Local Launcher
REM Starts:
REM - Konnaxion Agent on 127.0.0.1:8765
REM - Konnaxion Capsule Manager GUI on 127.0.0.1:8714
REM ============================================================

set "PROJECT_ROOT=%~dp0"
set "MANAGER_HOST=127.0.0.1"
set "MANAGER_PORT=8714"
set "AGENT_HOST=127.0.0.1"
set "AGENT_PORT=8765"

cd /d "%PROJECT_ROOT%"

echo.
echo ==========================================
echo Konnaxion Capsule Manager Local Launcher
echo Project: %PROJECT_ROOT%
echo ==========================================
echo.

where uv >nul 2>nul
if errorlevel 1 (
    echo ERROR: uv was not found in PATH.
    echo Install uv or open this from an environment where uv is available.
    pause
    exit /b 1
)

echo Checking Python/package imports...
uv run python -c "import kx_agent; import kx_manager; import kx_manager.ui.server; print('imports ok')"
if errorlevel 1 (
    echo.
    echo ERROR: Import check failed.
    pause
    exit /b 1
)

echo.
echo Starting Konnaxion Agent...
start "Konnaxion Agent" cmd /k "cd /d "%PROJECT_ROOT%" && uv run kx-agent run"

echo Waiting for Agent startup...
timeout /t 3 /nobreak >nul

echo.
echo Starting Konnaxion Capsule Manager GUI...
start "Konnaxion Capsule Manager" cmd /k "cd /d "%PROJECT_ROOT%" && uv run kx-manager --host %MANAGER_HOST% --port %MANAGER_PORT%"

echo Waiting for Manager startup...
timeout /t 4 /nobreak >nul

echo.
echo Opening GUI...
start "" "http://%MANAGER_HOST%:%MANAGER_PORT%/ui"

echo.
echo ==========================================
echo Started.
echo Agent:   http://%AGENT_HOST%:%AGENT_PORT%/v1/health
echo Manager: http://%MANAGER_HOST%:%MANAGER_PORT%/ui
echo Docs:    http://%MANAGER_HOST%:%MANAGER_PORT%/docs
echo ==========================================
echo.
echo Close the Agent and Manager terminal windows to stop services.
echo.

pause
endlocal