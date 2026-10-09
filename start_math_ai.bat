@echo off
chcp 65001 >nul
title 高中数学智能学习系统

cd /d E:\Projects\math_ai

echo ========================================
echo   高中数学智能学习系统
echo ========================================
echo.
echo 正在启动系统，请稍候...
echo.

"E:\anaconda3\python.exe" -m streamlit run app.py

echo.
echo 系统已停止。
pause