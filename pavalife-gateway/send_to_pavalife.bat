@echo off
REM ============================================================
REM  Gateway_IoT_PavaLife - BAN DU LIEU LEN SERVER THAT
REM  -> wss://iot-check.pavalife.com:443/mqtt  (MQTT 5.0 over WSS)
REM  User/pass lay tu gateway\registry.py (da cau hinh san).
REM ============================================================
setlocal
cd /d "%~dp0"
echo ==========================================================
echo  PavaLife - gui du lieu len iot-check.pavalife.com
echo ==========================================================

where py >nul 2>nul && (set "PY=py -3") || (where python >nul 2>nul && (set "PY=python") || (echo [LOI] Chua cai Python 3. & pause & exit /b 1))

echo.
echo [1/3] Cai thu vien...
%PY% -m pip install -r requirements.txt --quiet || (echo [LOI] cai thu vien that bai & pause & exit /b 1)

echo.
echo [2/3] Chan doan ket noi server (broker_check)...
%PY% tools\broker_check.py
if errorlevel 1 (
  echo.
  echo [CANH BAO] Chan doan chua PASS - xem goi y [-^>] o tren. Van tiep tuc?
  pause
)

echo.
echo [3/3] Gui tat ca ban tin len server...
%PY% pvl_send.py all --publish
echo.
echo ==========================================================
echo  Xong. Nhan phim de GUI LAI, hoac dong cua so de dung.
echo ==========================================================
pause >nul
%PY% pvl_send.py all --publish
pause
