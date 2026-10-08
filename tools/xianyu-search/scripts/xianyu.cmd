@echo off
rem Windows convenience wrapper: uses the skill-local .venv when present.
setlocal
set "ROOT=%~dp0.."
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\scripts\xianyu.py" %*
) else (
  python "%ROOT%\scripts\xianyu.py" %*
)
endlocal
