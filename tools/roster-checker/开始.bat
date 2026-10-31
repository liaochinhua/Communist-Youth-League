@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ---- 找 Python ----
set PY=
if exist "python路径.txt" set /p PY=<python路径.txt
if defined PY if not exist "!PY!" set PY=
if not defined PY (
  where python >nul 2>nul && set PY=python
)
if not defined PY (
  where py >nul 2>nul && set PY=py
)
if not defined PY (
  echo 没找到 Python，请先安装 Python 3.8+ 并勾选 "Add to PATH"
  pause & exit /b 1
)

:menu
cls
echo ============================================================
echo    团员花名册核查工具
echo ============================================================
echo.
echo   1  运行前检查（配置、文件、依赖）
echo   2  读表检查（确认脚本看懂你的表）
echo   3  生成 / 更新专业简称表
echo   4  核查表格自身问题（籍贯、时间格式、备注、重复）
echo   5  与智慧团建对账（缺失、班级不符）
echo   6  出名单（提交版 + 复核版）
echo   7  人数统计（按学院 / 按班级 / 缺失名单）
echo   8  按学院拆分（发给学院负责人）
echo   9  一键全跑（4 -^> 5 -^> 6 -^> 7 -^> 8）
echo.
echo   0  退出
echo.
set /p CH=请输入编号:

if "%CH%"=="1" goto check
if "%CH%"=="2" goto readcheck
if "%CH%"=="3" goto short
if "%CH%"=="4" goto step3
if "%CH%"=="5" goto step4
if "%CH%"=="6" goto step5
if "%CH%"=="7" goto step6
if "%CH%"=="8" goto step7
if "%CH%"=="9" goto all
if "%CH%"=="0" exit /b 0
goto menu

:check
cls
if not exist "config.json" (
  echo [!] 没有 config.json
  echo     请把 config.example.json 复制一份，改名为 config.json，再填路径。
  echo.
  pause & goto menu
)
%PY% -c "import openpyxl" 2>nul
if errorlevel 1 (
  echo [!] 缺少 openpyxl，正在安装...
  %PY% -m pip install openpyxl
)
%PY% -c "import conf; print('花名册 :', conf.roster_file()); print('系统名单:', conf.sys_csv()); print('输出目录:', conf.OUT_DIR); print('核查学院:', conf.COLLEGES)"
echo.
pause & goto menu

:readcheck
%PY% "scripts\2_读表检查.py"
echo.
pause & goto menu

:short
%PY% "scripts\8_生成简称表.py"
echo.
pause & goto menu

:step3
%PY% "scripts\3_核查_表格内.py"
echo.
pause & goto menu

:step4
%PY% "scripts\4_对账.py"
echo.
pause & goto menu

:step5
%PY% "scripts\5_出总表.py"
echo.
pause & goto menu

:step6
%PY% "scripts\6_人数统计.py"
echo.
pause & goto menu

:step7
%PY% "scripts\7_分学院.py"
echo.
pause & goto menu

:all
%PY% "scripts\2_读表检查.py"
%PY% "scripts\3_核查_表格内.py"
if errorlevel 1 (echo 第3步失败 & pause & goto menu)
%PY% "scripts\4_对账.py"
if errorlevel 1 (echo 第4步失败 & pause & goto menu)
%PY% "scripts\5_出总表.py"
%PY% "scripts\6_人数统计.py"
%PY% "scripts\7_分学院.py"
echo.
echo 全部完成，结果在 输出\ 目录。
pause & goto menu
