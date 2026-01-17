#!/bin/bash
# macOS Build Script for SegmentGrabber

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Building macOS executable..."
pyinstaller --onefile --windowed --name "SegmentGrabber" main.py

echo "Build complete!"
echo "App is in: dist/SegmentGrabber.app"
