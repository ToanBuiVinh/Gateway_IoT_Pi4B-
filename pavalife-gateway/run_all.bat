@echo off
REM ============================================================
REM  PavaLife Gateway - chay toan bo pipeline theo Contract v2.1
REM  Sinh ban tin mau + validate (schema 2020-12) + trang web
REM ============================================================
setlocal
cd /d "%~dp0"
echo ==========================================================
echo  PavaLife Device Data Contract v2.1 - 6 thiet bi
echo ==========================================================

where py >nul 2>nul && (set "PY=py -3") || (where python >nul 2>nul && (set "PY=python") || (echo [LOI] Chua cai Python 3. & pause & exit /b 1))
echo Dung Python: %PY%

echo.
echo [1/4] Cai thu vien...
%PY% -m pip install -r requirements.txt --quiet || (echo [LOI] cai thu vien that bai & pause & exit /b 1)

echo.
echo [2/4] Sinh 9 ban tin mau...
%PY% tools\gen_samples.py || goto :fail

echo.
echo [3/4] Kiem thu (schema 2020-12 + rule #7/#8/#10)...
%PY% tests\test_contract.py || goto :fail

echo.
echo [4/4] Sinh trang web dashboard...
%PY% tools\gen_viewer.py || goto :fail

echo.
echo ==========================================================
echo  HOAN TAT. Mo dashboard...
echo ==========================================================
start "" "%~dp0viewer\index.html"
echo Output: samples\  viewer\index.html
echo Gui thu 1 ban tin ra man hinh: %PY% pvl_send.py vitals --devices spo2
pause
exit /b 0
:fail
echo. & echo [LOI] Pipeline that bai. & pause & exit /b 1
