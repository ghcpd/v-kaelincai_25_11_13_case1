#!/bin/bash
# Setup script for Project A

echo "=== Setting up Project A (Legacy v1 integration) ==="

# Create virtual environment
python -m venv venv

# Activate virtual environment
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Install dependencies
pip install -r requirements.txt

# Create log directories
mkdir -p logs results

echo "=== Setup complete for Project A ==="
