#!/bin/bash
# Run the full production test suite
# Requires: server running on port 8000

cd backend
../.venv/Scripts/python.exe test_step2_production.py
