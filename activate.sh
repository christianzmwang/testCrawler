#!/bin/bash
# Activation script for the virtual environment

source venv/bin/activate
echo "✅ Virtual environment activated!"
echo "Python: $(which python)"
echo "Pip: $(which pip)"
echo ""
echo "To run the crawler:"
echo "  python crawler.py"
echo ""
echo "To deactivate when done:"
echo "  deactivate"

