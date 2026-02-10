#!/bin/bash
# macOS Build Script for SegmentGrabber

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Building macOS executable..."
pyinstaller --onedir --windowed --name "SegmentGrabber" main.py

echo "Build complete!"
echo "App is in: dist/SegmentGrabber.app"
