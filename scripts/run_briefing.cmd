@echo off
rem Runs one briefing slot. Windows Task Scheduler calls this (see register_tasks.ps1);
rem it also works by hand:
rem   scripts\run_briefing.cmd kr_open
rem   scripts\run_briefing.cmd us_open
rem The exit code is the job's exit code, so the scheduler's "last run result" means something.
rem Output of the last run per slot: logs\<slot>.log. One summary line per run: logs\history.log.
setlocal
set SLOT=%~1
if "%SLOT%"=="" (
    echo usage: run_briefing.cmd kr_open^|us_open
    exit /b 64
)
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Repository root = parent of this script. Settings read .env from the current directory.
for %%I in ("%~dp0..") do set ROOT=%%~fI
set UV=%USERPROFILE%\.local\bin\uv.exe
set DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe
if not exist "%DOCKER%" set DOCKER=docker
set LOGDIR=%ROOT%\logs
set LOG=%LOGDIR%\%SLOT%.log
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
cd /d "%ROOT%"

echo === start %DATE% %TIME% slot=%SLOT% === > "%LOG%"
git branch --show-current >> "%LOG%" 2>&1

rem Right after login the Docker engine is still starting: wait up to ~2 minutes.
set TRIES=0
:wait_docker
"%DOCKER%" info >nul 2>&1 && goto docker_ready
set /a TRIES+=1
if %TRIES% geq 12 (
    echo === docker engine not ready after %TRIES% tries === >> "%LOG%"
    set RC=2
    goto finish
)
ping -n 11 127.0.0.1 >nul
goto wait_docker

:docker_ready
rem The job needs the local database.
"%DOCKER%" compose --profile db up -d --wait >> "%LOG%" 2>&1
if errorlevel 1 (
    echo === docker compose failed === >> "%LOG%"
    set RC=2
    goto finish
)

"%UV%" run python -m finbrief_analyzer.jobs.run_briefing --slot %SLOT% >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%

:finish
echo === exit %RC% %DATE% %TIME% === >> "%LOG%"
echo %DATE% %TIME% %SLOT% rc=%RC% >> "%LOGDIR%\history.log"
endlocal & exit /b %RC%
