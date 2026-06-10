@echo off
echo Installing / checking editor dependencies...
pip install -r scenario_editor\requirements.txt --quiet
echo.
echo Starting OpenMATB Scenario Editor...
python -m streamlit run scenario_editor\app.py
pause
