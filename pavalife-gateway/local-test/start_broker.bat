@echo off
REM Khoi dong broker Mosquitto cuc bo (KHONG can Docker)
cd /d "%~dp0"
where mosquitto >nul 2>nul
if %errorlevel% neq 0 (
  echo [LOI] Chua cai Mosquitto.
  echo   Cai nhanh bang 1 lenh:   winget install EclipseFoundation.Mosquitto
  echo   Hoac tai tai:            https://mosquitto.org/download/
  echo   Sau khi cai, mo lai file nay.
  pause
  exit /b 1
)
echo Khoi dong Mosquitto (1883 MQTT, 9001 WebSocket)... Ctrl+C de dung.
mosquitto -c mosquitto.conf -v
