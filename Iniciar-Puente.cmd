@echo off
title Muldraugh Afterdark FM - Puente local
cd /d "%~dp0"
python bridge\pear_bridge.py %*
pause
