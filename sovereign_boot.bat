@echo off
chcp 65001 >nul
title MiroFish Sovereign V7 — Boot Sequence
color 0B
cls

echo.
echo  ███╗   ███╗██╗██████╗  ██████╗ ███████╗██╗███████╗██╗  ██╗
echo  ████╗ ████║██║██╔══██╗██╔═══██╗██╔════╝██║██╔════╝██║  ██║
echo  ██╔████╔██║██║██████╔╝██║   ██║█████╗  ██║███████╗███████║
echo  ██║╚██╔╝██║██║██╔══██╗██║   ██║██╔══╝  ██║╚════██║██╔══██║
echo  ██║ ╚═╝ ██║██║██║  ██║╚██████╔╝██║     ██║███████║██║  ██║
echo  ╚═╝     ╚═╝╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝
echo.
echo  SOVEREIGN V7 — Autonomous VFL Trading Engine
echo  ─────────────────────────────────────────────
echo.

:: ── Step 1: Kill stale processes ─────────────────────────────────────────────
echo  [1/4] Terminating stale Python processes...
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
echo        Done.

:: ── Step 2: Ensure log directory ─────────────────────────────────────────────
echo  [2/4] Preparing log directory...
if not exist "ANalysis\logs" mkdir "ANalysis\logs"
echo        ANalysis\logs ready.

:: ── Step 3: Launch Oracle Server ─────────────────────────────────────────────
echo  [3/4] Launching Oracle Server (V7)...
start /B python scripts\server.py >> ANalysis\logs\server.log 2>&1
echo        Server started. Waiting for init...
timeout /t 5 /nobreak >nul

:: Verify server is responding
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/status', timeout=5)" >nul 2>&1
if %errorlevel% == 0 (
    echo        [OK] Server responded on port 5000.
) else (
    echo        [WARN] Server may still be starting — check ANalysis\logs\server.log
)

:: ── Step 4: Launch Scavenger Daemon ──────────────────────────────────────────
echo  [4/4] Launching Scavenger Daemon (V4)...
start /B python scripts\scavenger_daemon.py >> ANalysis\logs\scavenger.log 2>&1
echo        Daemon started.
timeout /t 2 /nobreak >nul

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  ─────────────────────────────────────────────
echo  SYSTEM ONLINE
echo  Dashboard : http://127.0.0.1:5000
echo  Server Log: ANalysis\logs\server.log
echo  Daemon Log: ANalysis\logs\scavenger.log
echo  ─────────────────────────────────────────────
echo.

:: Open dashboard
start http://127.0.0.1:5000

echo  Press any key to tail the server log (CTRL+C to stop)...
pause >nul
type ANalysis\logs\server.log
