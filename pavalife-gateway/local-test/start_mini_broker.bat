@echo off
REM Broker MQTT thuan Python - KHONG can tai gi, chi can Python
cd /d "%~dp0"
echo mini_broker (Python thuan) tren mqtt://localhost:1883 ...
python mini_broker.py
pause
