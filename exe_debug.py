#!/usr/bin/env python3
"""
Diagnostic script to help debug exe crashes.
Run this from the exe folder to check if all paths and files are set up correctly.
"""

import os
import sys
from pathlib import Path

def check_exe_environment():
    """Check if the exe environment is set up correctly."""
    print("=" * 70)
    print("OpenMATB EXE Environment Diagnostic")
    print("=" * 70)
    
    # Check if we're in a frozen exe
    is_frozen = getattr(sys, 'frozen', False)
    print(f"\n1. Frozen executable? {is_frozen}")
    print(f"   sys.executable: {sys.executable}")
    print(f"   sys.prefix: {sys.prefix}")
    
    # Check current working directory
    cwd = os.getcwd()
    print(f"\n2. Current working directory: {cwd}")
    
    # Check if key files exist
    print("\n3. Required files:")
    required_files = ['config.ini', 'VERSION', 'main.py']
    for fname in required_files:
        fpath = Path(cwd) / fname
        exists = "✓" if fpath.exists() else "✗"
        print(f"   {exists} {fname}: {fpath}")
    
    # Check if required directories exist
    print("\n4. Required directories:")
    required_dirs = ['includes', 'locales', 'core', 'plugins']
    for dname in required_dirs:
        dpath = Path(cwd) / dname
        exists = "✓" if dpath.exists() else "✗"
        print(f"   {exists} {dname}/: {dpath}")
    
    # Check config.ini
    print("\n5. Config file check:")
    config_path = Path(cwd) / 'config.ini'
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                lines = f.readlines()
            print(f"   ✓ config.ini readable ({len(lines)} lines)")
            
            # Find scenario path
            for line in lines:
                if 'scenario_path=' in line:
                    scenario_path = line.split('=', 1)[1].strip()
                    print(f"   Scenario configured: {scenario_path}")
                    
                    # Check if scenario exists
                    scenario_file = Path(cwd) / 'includes' / 'scenarios' / scenario_path
                    if scenario_file.exists():
                        print(f"   ✓ Scenario file found: {scenario_file}")
                    else:
                        print(f"   ✗ Scenario file NOT found: {scenario_file}")
                    break
        except Exception as e:
            print(f"   ✗ Error reading config.ini: {e}")
    else:
        print(f"   ✗ config.ini not found")
    
    # Check Python version and modules
    print("\n6. Python environment:")
    print(f"   Python version: {sys.version}")
    
    critical_modules = ['pyglet', 'pathlib']
    print(f"   Critical modules:")
    for mod_name in critical_modules:
        try:
            __import__(mod_name)
            print(f"   ✓ {mod_name}")
        except ImportError:
            print(f"   ✗ {mod_name} NOT FOUND")
    
    print("\n" + "=" * 70)
    print("If you see ✗ marks above, those are likely the cause of crashes.")
    print("=" * 70)

if __name__ == '__main__':
    check_exe_environment()
    print("\nDiagnostics complete. Press Enter to close.")
    input()
