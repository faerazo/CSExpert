#!/bin/bash
# Quick activation script for CSExpert environment

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "CSExpert environment activated"
    echo "Python: $(which python)"
    echo "Version: $(python --version)"
else
    echo "Virtual environment not found. Run ./setup.sh first"
fi