#!/usr/bin/env bash
set -e

echo "========================================"
echo "FrankieXGM Linux Build"
echo "========================================"
echo

echo "Installing/updating PyInstaller..."
python3 -m pip install --upgrade pyinstaller

echo
echo "Building FrankieXGM..."

pyinstaller --onefile --name FrankieXGM_GUI FrankieXGM_GUI.py

echo
echo "========================================"
echo "Build complete!"
echo "========================================"
echo
echo "Executable:"
echo "  dist/FrankieXGM_GUI"
echo