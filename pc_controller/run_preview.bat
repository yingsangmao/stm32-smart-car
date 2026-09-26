@echo off
rem ===========================================================
rem  Gesture control - PREVIEW mode
rem  Camera only. Does NOT connect to the car, sends nothing.
rem  Press q or ESC in the window to quit.
rem
rem  Moved to another PC? Edit the python.exe path below.
rem  Chinese docs: see README.md in this folder.
rem ===========================================================
chcp 936 >nul
cd /d "%~dp0"
"D:\Anaconda\envs\car-gesture\python.exe" gesture_preview.py --min-score 0.50 %*
echo.
echo Program exited.
pause
