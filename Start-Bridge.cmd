@echo off
title Muldraugh Afterdark FM - Local bridge
cd /d "%~dp0"
if exist "dist\0.5.0\MuldraughAfterdarkFM.exe" (
    start "" "dist\0.5.0\MuldraughAfterdarkFM.exe"
    exit /b
)
rem Developer fallback only. Players use the standalone companion download.
python bridge\pear_bridge.py %*
pause
