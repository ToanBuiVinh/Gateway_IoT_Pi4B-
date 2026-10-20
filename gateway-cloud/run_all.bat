@echo off
REM ============================================================
REM  Medical IoT Gateway - chay toan bo pipeline Python
REM  Sinh 10 payload MQTT + 10 Bundle FHIR + validate + trang web
REM ============================================================
setlocal
cd /d "%~dp0"

echo ==========================================================
echo  Medical Gateway - Data Contract (10 thiet bi)
echo ==========================================================

REM --- 1) Tim Python ---
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo [LOI] Khong tim thay Python. Cai Python 3 tai https://www.python.org/downloads/
    pause
    exit /b 1
  )
)
echo Dung Python: %PY%

REM --- 2) Cai thu vien ---
echo.
echo [1/5] Cai thu vien (jsonschema, paho-mqtt)...
%PY% -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
  echo [LOI] Cai thu vien that bai.
  pause
  exit /b 1
)

REM --- 3) Sinh payload MQTT ---
echo.
echo [2/5] Sinh 10 payload MQTT...
%PY% tools\gen_samples.py
if %errorlevel% neq 0 goto :fail

REM --- 4) Sinh Bundle FHIR ---
echo.
echo [3/5] Sinh 10 Bundle FHIR...
%PY% tools\gen_fhir.py
if %errorlevel% neq 0 goto :fail

REM --- 5) Kiem thu hop dong ---
echo.
echo [4/5] Kiem thu (schema + range + UCUM + mapper)...
%PY% tests\test_contract.py
if %errorlevel% neq 0 goto :fail

REM --- 6) Sinh trang web dashboard ---
echo.
echo [5/5] Sinh trang web dashboard...
%PY% tools\gen_viewer.py
if %errorlevel% neq 0 goto :fail

echo.
echo ==========================================================
echo  HOAN TAT. Mo trang web dashboard...
echo ==========================================================
start "" "%~dp0viewer\index.html"
echo Output: samples\mqtt\  samples\fhir\  viewer\index.html
pause
exit /b 0

:fail
echo.
echo [LOI] Pipeline that bai o buoc tren. Xem thong bao loi phia tren.
pause
exit /b 1
