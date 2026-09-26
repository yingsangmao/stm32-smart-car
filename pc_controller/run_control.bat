@echo off
rem ===========================================================
rem  Gesture control - ACTUAL CONTROL
rem  Camera + Bluetooth. This really drives the car.
rem  Put the wheels off the ground for the first test!
rem
rem  --port auto picks the Bluetooth port that is really bound to
rem  a device, and skips the adapter's generic incoming port
rem  (that one can never reach the car). If it picks wrong,
rem  replace it with the exact port, e.g. --port COM4
rem
rem  Moved to another PC? Edit the python.exe path below.
rem  Chinese docs: see README.md in this folder.
rem ===========================================================
chcp 936 >nul
cd /d "%~dp0"
"D:\Anaconda\envs\car-gesture\python.exe" gesture_control.py --port auto --min-score 0.50 %*
echo.
echo Program exited. Serial port released.
pause
