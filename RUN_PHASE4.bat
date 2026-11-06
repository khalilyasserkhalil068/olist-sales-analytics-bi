@echo off
setlocal
title Olist Phase 4 - SQL Server Execution
cd /d "%~dp0"
if errorlevel 1 goto bad_directory
set "PHASE4_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PHASE4_LAUNCHER=%~dp0scripts\phase4\launch_phase4.py"
set "PHASE4_REPORT=%~dp0reports\phase_4_terminal_run\phase_4_execution_report.md"
set "PYTHONDONTWRITEBYTECODE=1"
echo.
echo Olist Phase 4 - DESKTOP-GEUMHVT\SQLEXPRESS
echo This launcher requires typed confirmation before database execution.
echo.
if not exist "%PHASE4_PYTHON%" goto missing_python
if not exist "%PHASE4_LAUNCHER%" goto missing_launcher
"%PHASE4_PYTHON%" "%PHASE4_LAUNCHER%" --project "%~dp0."
set "PHASE4_EXIT=%ERRORLEVEL%"
echo.
if "%PHASE4_EXIT%"=="0" echo Execution returned successfully. See the report for actual validation evidence.
if not "%PHASE4_EXIT%"=="0" echo Phase 4 stopped or was cancelled. Exit code: %PHASE4_EXIT%
echo Report: "%PHASE4_REPORT%"
echo.
pause
exit /b %PHASE4_EXIT%

:missing_python
echo ERROR: Project Python was not found:
echo "%PHASE4_PYTHON%"
echo Restore the existing project .venv before continuing.
goto preparation_error

:missing_launcher
echo ERROR: Phase 4 launcher was not found:
echo "%PHASE4_LAUNCHER%"
goto preparation_error

:preparation_error
if not exist "%~dp0reports\phase_4_terminal_run" mkdir "%~dp0reports\phase_4_terminal_run"
if not exist "%PHASE4_REPORT%" (
  > "%PHASE4_REPORT%" echo # Phase 4 execution report
  >> "%PHASE4_REPORT%" echo.
  >> "%PHASE4_REPORT%" echo Status: NOT EXECUTED / NOT COMPLETE. Launcher prerequisites are missing.
)
echo No SQL connection or ETL was attempted.
echo Report: "%PHASE4_REPORT%"
pause
exit /b 1

:bad_directory
echo ERROR: Could not open the project folder. Keep this file in the project root.
pause
exit /b 1
