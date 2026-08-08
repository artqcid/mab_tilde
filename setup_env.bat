@echo off
REM Setup script for mab_tilde Python environment
REM Run this script to create a virtual environment and install dependencies

echo Setting up mab_tilde Python environment...

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0

REM Create virtual environment if it doesn't exist
if not exist "%SCRIPT_DIR%.venv" (
    echo Creating virtual environment...
    python -m venv "%SCRIPT_DIR%.venv"
)

REM Activate virtual environment
echo Activating virtual environment...
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing requirements...
pip install -r "%SCRIPT_DIR%requirements.txt"

echo.
echo Setup complete!
echo To activate the environment in the future, run:
echo   call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
echo.
echo Or use the full path to python:
echo   "%SCRIPT_DIR%.venv\Scripts\python.exe"

pause