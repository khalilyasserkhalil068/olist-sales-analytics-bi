@echo off
setlocal
set "PROJECT=E:\Projects CV\Sales Analytics & Business Intelligence"
if not exist "%PROJECT%\.venv\Scripts\python.exe" (
  echo ERROR: Project .venv Python was not found.
  pause
  exit /b 1
)
echo Phase 4 tests only - no ETL and no database recreation.
"%PROJECT%\.venv\Scripts\python.exe" -B "%~dp0run_phase4_tests_only.py" --project "%PROJECT%"
set "RESULT=%ERRORLEVEL%"
echo.
echo Test runner exit code: %RESULT%
pause
exit /b %RESULT%
