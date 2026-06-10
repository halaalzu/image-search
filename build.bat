@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo  OpenMATB -- PyInstaller build
echo ============================================================
echo.

:: ---------------------------------------------------------------
:: 1. Make sure we are in the project root (where this .bat lives)
:: ---------------------------------------------------------------
cd /d "%~dp0"

:: ---------------------------------------------------------------
:: 2. Locate Python — prefer the project .venv if it exists,
::    otherwise fall back to whatever 'python' is on PATH.
:: ---------------------------------------------------------------
set VENV_PYTHON=%~dp0.venv\Scripts\python.exe
if exist "%VENV_PYTHON%" (
    set PYTHON=%VENV_PYTHON%
    echo [1/4] Using project .venv Python: %VENV_PYTHON%
) else (
    set PYTHON=python
    echo [1/4] .venv not found -- using system Python.
)

echo        Installing / upgrading PyInstaller...
"%PYTHON%" -m pip install --upgrade pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: pip install failed. Check that Python is available.
    pause & exit /b 1
)
echo        Installing scenario editor dependencies...
"%PYTHON%" -m pip install -r scenario_editor\requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: failed to install scenario editor dependencies.
    pause & exit /b 1
)
echo        Done.
echo.

:: ---------------------------------------------------------------
:: 3. Install UPX (optional -- compresses the exe a bit)
::    Skip quietly if it can't be fetched.
:: ---------------------------------------------------------------
where upx >nul 2>&1
if %errorlevel% neq 0 (
    echo [2/4] UPX not found -- bundle will not be compressed ^(that is OK^).
) else (
    echo [2/4] UPX found -- binary compression enabled.
)
echo.

:: ---------------------------------------------------------------
:: 4. Clean previous build artifacts
:: ---------------------------------------------------------------
echo [3/4] Cleaning previous build...
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist
echo        Done.
echo.

:: ---------------------------------------------------------------
:: 5. Run PyInstaller
:: ---------------------------------------------------------------
echo [4/4] Building OpenMATB -- this takes 1-3 minutes...
echo.
"%PYTHON%" -m PyInstaller openmatb.spec --clean --noconfirm --distpath release

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo  BUILD FAILED  -- scroll up to read the error.
    echo ============================================================
    pause & exit /b 1
)

echo.
echo [5/5] Building Scenario Editor bundle...
"%PYTHON%" -m PyInstaller scenario_editor.spec --clean --noconfirm --distpath release\openmatb
if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo  SCENARIO EDITOR BUILD FAILED  -- scroll up to read the error.
    echo ============================================================
    pause & exit /b 1
)

:: ---------------------------------------------------------------
:: 6. Write a quick launch helper next to the exe
:: ---------------------------------------------------------------
echo @echo off> release\openmatb\run.bat
echo cd /d "%%~dp0">> release\openmatb\run.bat
echo openmatb.exe>> release\openmatb\run.bat
echo @echo off> release\openmatb\run_editor.bat
echo cd /d "%%~dp0\scenario_editor">> release\openmatb\run_editor.bat
echo scenario_editor.exe>> release\openmatb\run_editor.bat

echo.
echo ============================================================
echo  BUILD SUCCEEDED
echo.
echo  Output folder : release\openmatb\
echo  Launch exe    : release\openmatb\openmatb.exe
echo                  (or double-click release\openmatb\run.bat)
echo  Editor exe    : release\openmatb\scenario_editor\scenario_editor.exe
echo                  (or double-click release\openmatb\run_editor.bat)
echo.
echo  To share with another computer:
echo    zip the entire release\openmatb\ folder and copy it over.
echo    The recipient unzips and runs openmatb.exe -- no Python needed.
echo.
echo  Session data (logs, recordings) will be saved inside the
echo  release\openmatb\_internal\sessions\ folder on first run.
echo ============================================================
echo.
pause
