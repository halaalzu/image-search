#!/usr/bin/env python3
"""
OpenMATB Scenario Editor Launcher
This script launches the Streamlit-based scenario editor.
Can be compiled to an EXE using PyInstaller.

Usage:
    python launch_editor.py
    
Or compile to EXE:
    pip install pyinstaller
    pyinstaller --onefile --icon=app.ico launch_editor.py
"""

import sys
import os
import subprocess
import platform
import webbrowser
from pathlib import Path
import time

def get_script_dir():
    """Get the directory where this script is located"""
    return Path(__file__).resolve().parent

def check_python_version():
    """Check if Python version is 3.9 or higher"""
    if sys.version_info < (3, 9):
        print("Error: Python 3.9 or higher is required")
        print(f"Your version: {sys.version}")
        input("Press Enter to exit...")
        sys.exit(1)

def install_packages():
    """Install required packages if not already installed"""
    packages = ['streamlit', 'plotly', 'pandas']
    
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', package])

def main():
    """Main launcher function"""
    try:
        print("=" * 60)
        print("OpenMATB Scenario Editor")
        print("=" * 60)
        
        # Check Python version
        check_python_version()
        
        # Change to script directory
        script_dir = get_script_dir()
        os.chdir(script_dir)
        
        # Install packages if needed
        print("\nChecking dependencies...")
        install_packages()
        
        # Launch Streamlit
        print("\nStarting Scenario Editor...")
        print("Opening browser to http://localhost:8501")
        print("\nPress Ctrl+C to stop the server")
        print("=" * 60)
        
        # Give browser a moment to launch
        time.sleep(2)
        try:
            webbrowser.open('http://localhost:8501')
        except Exception:
            pass
        
        # Run Streamlit
        subprocess.run([
            sys.executable, '-m', 'streamlit', 'run',
            'scenario_editor/app.py'
        ])
        
    except KeyboardInterrupt:
        print("\n\nScenario Editor stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        input("Press Enter to exit...")
        sys.exit(1)

if __name__ == '__main__':
    main()
