@echo off
title Muldraugh Afterdark FM - Local bridge
cd /d "%~dp0"
python bridge\pear_bridge.py %*
pause
