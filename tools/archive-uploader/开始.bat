@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 团委档案上传工具

rem ---------- 找 Python ----------
set "PY="
if exist "python路径.txt" set /p PY=<"python路径.txt"
if not defined PY (
  for /d %%D in ("%USERPROFILE%\.dsh\dsh-runtimes\*") do (
    if exist "%%D\dependencies\python\python.exe" set "PY=%%D\dependencies\python\python.exe"
  )
)
if not defined PY (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    "%%P" -V >nul 2>&1 && set "PY=%%P"
  )
)
if not defined PY (
  echo.
  echo   [x] 没找到 Python。请把完整的 python.exe 路径写进本目录的 python路径.txt
  echo.
  pause
  exit /b 1
)

:menu
cls
echo ==========================================================
echo            团委档案批量上传工具
echo ==========================================================
echo   Python : %PY%
echo   清单   : 输出\upload_plan.csv
echo ==========================================================
echo   [1] 自检        （查网络、查文件齐不齐）
echo   [2] 生成匹配表  （输出\records.csv 更新后跑）
echo   [3] 演练        （不写服务器，看会传哪些）
echo   [4] 先传 1 个    （真传一条，验证没问题）
echo   [5] 全部上传    （断点续传，失败可重跑）
echo   [6] 核对结果    （新的 records.csv 改名 records_after.csv）
echo   [7] 抓页面结构  （我要看页面 HTML 时用）
echo   [8] 清理重复附件（同一记录里同长度的只留一个）
echo   [9] 全面体检    （逐条比对本地文件大小，最后核对用）
echo  [10] 对账修正    （缺的补传、旧附件删掉，只留一致的那份）
echo   [0] 退出
echo ==========================================================
set "CH="
set /p "CH=请输入序号后回车："

if "%CH%"=="1" goto s1
if "%CH%"=="2" goto s2
if "%CH%"=="3" goto s3
if "%CH%"=="4" goto s4
if "%CH%"=="5" goto s5
if "%CH%"=="6" goto s6
if "%CH%"=="7" goto s7
if "%CH%"=="8" goto s8
if "%CH%"=="9" goto s9
if "%CH%"=="10" goto s10
if "%CH%"=="0" exit /b 0
goto menu

:s1
cls
"%PY%" "scripts\0_自检.py"
echo.
pause
goto menu

:s2
cls
if not exist "输出\records.csv" (
  echo   [x] 没找到 输出\records.csv
  echo       先把浏览器导出的 records.csv 复制到 输出\ 目录
  echo.
  pause
  goto menu
)
"%PY%" "scripts\2_生成匹配表.py" --records "输出\records.csv"
echo.
echo   生成完毕。Excel 打开 输出\upload_plan.csv，重点看「状态」列。
echo.
pause
goto menu

:s3
cls
if not defined CK call :getck
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --limit 5
echo.
pause
goto menu

:s4
cls
if not defined CK call :getck
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --limit 1 --commit
echo.
echo   传完到网页上确认：新文件在了吗？范芸的旧文件删掉了吗？
echo.
pause
goto menu

:s5
cls
if not defined CK call :getck
echo.
echo   即将全量上传。按 Ctrl+C 可随时停，重跑会接着上次的进度。
echo.
pause
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --commit
echo.
pause
goto menu

:s6
cls
if not exist "输出\records_after.csv" (
  echo   [x] 没找到 输出\records_after.csv
  echo       重新跑一次导出脚本，把新 records.csv 改名 records_after.csv 放进 输出\
  echo.
  pause
  goto menu
)
"%PY%" "scripts\4_核对.py" --after "输出\records_after.csv"
echo.
pause
goto menu

:s7
cls
if not defined CK call :getck
set "FID="
set /p "FID=输入记录id，直接回车用默认 1462："
if not defined FID set "FID=1462"
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --dump-form "%FID%"
echo.
echo   已保存 输出\form_%FID%.html
echo.
pause
goto menu

:s8
cls
if not defined CK call :getck
echo.
echo   === 第一步：只检查，不删除 ===
echo.
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --dedup
echo.
set "YN="
set /p "YN=确认删除重复的（每组保留一个）？输入 y 回车，其他键跳过："
if /i "%YN%"=="y" "%PY%" "scripts\3_上传.py" --cookie "%CK%" --dedup --commit
echo.
pause
goto menu

:s9
cls
if not defined CK call :getck
echo   全库体检：逐条打开 238 条记录，看附件和上传者，大约 2~3 分钟。
echo.
pause
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --audit
echo.
pause
goto menu

:s10
cls
if not defined CK call :getck
echo.
echo   === 只报告，不改动 ===
echo.
"%PY%" "scripts\3_上传.py" --cookie "%CK%" --reconcile
echo.
set "YN="
set /p "YN=确认按上面的清单补传并删旧附件？输入 y 回车："
if /i "%YN%"=="y" "%PY%" "scripts\3_上传.py" --cookie "%CK%" --reconcile --commit
echo.
pause
goto menu

:getck
set "CK="
echo.
echo   打开档案系统任意页面，按 F12 进控制台，输入  document.cookie  回车，
echo   把整串（形如 ASPSESSIONIDXXXX=...）复制，粘贴到下面。
echo.
set /p "CK=cookie："
if not defined CK goto getck
exit /b 0
