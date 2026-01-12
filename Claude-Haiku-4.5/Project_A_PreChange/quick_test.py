#!/usr/bin/env python
"""
Simple test runner for Project A
Executes unit tests
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Run unit tests
    print("\n" + "="*60)
    print("Running Project A Unit Tests")
    print("="*60 + "\n")
    
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_pre_unit.py", "-v", "--tb=short"],
        capture_output=False
    )
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
