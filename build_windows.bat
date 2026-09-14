@echo off
setlocal
cd /d "%~dp0"

echo Installing/updating PyInstaller...
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

echo Building FrankieXGM.exe...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name FrankieXGM --version-file=FrankieXGM_version.txt FrankieXGM_GUI.py
if errorlevel 1 goto :error

echo.
echo Build complete:
echo %CD%\dist\FrankieXGM.exe
pause
exit /b 0

:error
echo.
echo Build failed.
pause
exit /b 1
