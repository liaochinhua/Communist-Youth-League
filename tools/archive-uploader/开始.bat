@echo off
chcp 65001 >nul 2>nul
rem ==========================================================================
rem  Launcher for archive-uploader.
rem
rem  IMPORTANT: keep this file ASCII-only - both the text and every path it
rem  mentions. cmd.exe decodes batch files with the active code page; a
rem  batch file containing Chinese text can be split mid-character by the
rem  read buffer, and that line turns into a bogus command:
rem      "'xx' is not recognized as an internal or external command"
rem  All Chinese output lives in scripts\menu.py.
rem ==========================================================================

setlocal
cd /d "%~dp0"
set "PY="

rem ---- 1. explicit path from python-path.txt, if the user made one ----
if exist "python-path.txt" (
  set /p PY=<python-path.txt
  if defined PY call :verify "%PY%"
  if errorlevel 1 set "PY="
)

rem ---- 2. the py launcher ----
if not defined PY (
  where py >nul 2>nul && set "PY=py"
)

rem ---- 3. python.exe, skipping the 0-byte Microsoft Store stub ----
if not defined PY call :find_python

if not defined PY goto nopython

"%PY%" "scripts\menu.py"
if errorlevel 1 pause
exit /b 0

:nopython
cls
echo ============================================================
echo   Python not found
echo ============================================================
echo.
echo   This tool needs Python 3.8 or newer.
echo.
echo   1. Download from https://www.python.org/downloads/
echo      Tick "Add python.exe to PATH" during installation.
echo   2. Close this window and double-click the launcher again.
echo.
echo   If Python is already installed but you still see this:
echo      put the full path of python.exe into python-path.txt
echo      in this folder, one line, e.g.  C:\Python312\python.exe
echo.
pause
exit /b 1

rem ==========================================================================
rem  helpers
rem ==========================================================================

:verify
rem Check that a python command actually runs. %~1 may be "py" or a full path.
setlocal
"%~1" -c "import sys" >nul 2>nul
if errorlevel 1 (
  endlocal
  exit /b 1
)
endlocal
exit /b 0

:find_python
rem "where python" often returns the Microsoft Store placeholder first
rem (...\WindowsApps\python.exe), which is 0 bytes and cannot run.
for /f "delims=" %%p in ('where python 2^>nul') do (
  echo %%p | find /i "WindowsApps" >nul
  if errorlevel 1 (
    call :verify "%%p"
    if not errorlevel 1 (
      if not defined PY set "PY=%%p"
    )
  )
)
goto :eof
