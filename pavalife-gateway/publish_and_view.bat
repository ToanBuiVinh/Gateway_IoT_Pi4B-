@echo off
REM ============================================================
REM  PavaLife Gateway - PUBLISH + XEM DU LIEU TREN WEB (1 cu click)
REM  1) bat mini_broker (Python thuan, khong can tai gi)
REM  2) bat web_viewer  -> http://localhost:8080
REM  3) mo trinh duyet
REM  4) publish tat ca ban tin len broker cuc bo
REM  5) lap: nhan phim de gui lai
REM  Dong 2 cua so "mini_broker" / "web_viewer" de dung han.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PORT=8080"
set "URL=http://localhost:%PORT%"

echo ==========================================================
echo  PavaLife - Publish ^& Web Viewer (Contract v2.1)
echo ==========================================================

REM --- tim Python ---
where py >nul 2>nul && (set "PY=py -3") || (where python >nul 2>nul && (set "PY=python") || (echo [LOI] Chua cai Python 3. & pause & exit /b 1))
echo Dung Python: %PY%

echo.
echo [1/5] Cai thu vien (paho-mqtt, jsonschema)...
%PY% -m pip install -r requirements.txt --quiet || (echo [LOI] cai thu vien that bai & pause & exit /b 1)

echo.
echo [2/5] Bat mini_broker (mqtt://localhost:1883) o cua so rieng...
start "PavaLife mini_broker" cmd /k "%PY% local-test\mini_broker.py"
REM cho broker san sang
timeout /t 3 /nobreak >nul

echo.
echo [3/5] Bat web_viewer (%URL%) o cua so rieng...
start "PavaLife web_viewer" cmd /k "%PY% tools\web_viewer.py --http-port %PORT%"
timeout /t 3 /nobreak >nul

echo.
echo [4/5] Mo trinh duyet: %URL%
start "" "%URL%"
timeout /t 2 /nobreak >nul

:again
echo.
echo [5/5] Publish tat ca ban tin len broker cuc bo...
%PY% pvl_send.py all --local --publish
if errorlevel 1 (echo [LOI] publish that bai - broker da chay chua? & goto :ask)

REM --- audio FLAC (chi khi co 'flac' CLI tren PATH) ---
where flac >nul 2>nul && (
  echo.
  echo      + Gui ban tin ong nghe FLAC lossless that...
  %PY% audio\record_and_publish.py --publish --local
) || (
  echo.
  echo      [bo qua audio FLAC] chua co 'flac' CLI tren PATH.
  echo      Cai tai https://xiph.org/flac/download.html de bat duong luu ho so.
)

:ask
echo.
echo ==========================================================
echo  Xem du lieu tai: %URL%
echo  Nhan phim bat ky de GUI LAI, hoac dong cua so de dung.
echo ==========================================================
pause >nul
goto :again
