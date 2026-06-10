@echo off
REM OpenMATB Scenario Editor Launcher (Windows)
REM This batch file launches the Streamlit-based scenario editor

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.9+ and add it to your system PATH
    pause
    exit /b 1
)

REM Check if streamlit is installed
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo Installing required packages for Scenario Editor...
    pip install -q streamlit plotly pandas
    if errorlevel 1 (
        echo Error: Failed to install packages
        pause
        exit /b 1
    )
)

REM Launch the editor
echo Starting OpenMATB Scenario Editor...
echo Opening browser to http://localhost:8501
python -m streamlit run scenario_editor/app.py
