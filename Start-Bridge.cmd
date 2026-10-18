@echo off
title Afterdark FM Connector
cd /d "%~dp0"
if exist "dist\0.5.1\AfterdarkFMConnector.exe" (
    start "" "dist\0.5.1\AfterdarkFMConnector.exe"
    exit /b
)
rem Developer fallback only. Players use the standalone connector download.
python bridge\pear_bridge.py %*
pause
