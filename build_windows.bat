@echo off
REM Windows Build Script for SegmentGrabber
REM Run this script on Windows to create Windows executable

echo Installing dependencies...
pip install -r requirements.txt

echo Building Windows executable...
pyinstaller --onefile --windowed --name "SegmentGrabber" main.py

echo Build complete!
echo Executable is in: dist\SegmentGrabber.exe
pause
