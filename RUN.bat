@echo off
REM ==================================================================
REM  RUN.bat - Chay toan bo Medical Gateway sau khi pull tu GitHub
REM  Dat o GOC repo. Double-click la: cap nhat code + sinh du lieu +
REM  validate + mo trang web dashboard.
REM ==================================================================
setlocal
cd /d "%~dp0"

echo ==================================================================
echo  Medical IoT Gateway - 10 thiet bi
echo ==================================================================

REM --- Cap nhat code moi nhat tu GitHub (neu co git + la repo) ---
where git >nul 2>nul
if %errorlevel%==0 (
  if exist ".git" (
    echo Dang cap nhat code tu GitHub ^(git pull^)...
    git pull --ff-only
  ) else (
    echo [Bo qua] Thu muc nay chua phai git repo - dung code hien co.
  )
) else (
  echo [Bo qua] Khong tim thay git - dung code hien co.
)

REM --- Chay pipeline PavaLife v2.1 (hop dong hien hanh) ---
if not exist "pavalife-gateway\run_all.bat" (
  echo [LOI] Khong thay pavalife-gateway\run_all.bat . Ban da pull dung repo chua?
  pause
  exit /b 1
)
cd pavalife-gateway
call run_all.bat
