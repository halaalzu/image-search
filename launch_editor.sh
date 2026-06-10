#!/bin/bash
# OpenMATB Scenario Editor Launcher
# This script launches the Streamlit-based scenario editor

cd "$(dirname "$0")" || exit 1

# Check if streamlit is installed
if ! python3 -m streamlit --version &> /dev/null; then
    echo "Installing required packages for Scenario Editor..."
    pip3 install -q streamlit plotly pandas
fi

# Launch the editor
echo "Starting OpenMATB Scenario Editor..."
echo "Opening browser to http://localhost:8501"
python3 -m streamlit run scenario_editor/app.py
