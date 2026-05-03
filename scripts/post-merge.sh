#!/bin/bash
set -e

echo "=== Post-merge setup ==="

echo ">> Installing Python dependencies..."
pip install -r requirements-ci.txt --quiet --no-input

echo ">> Installing frontend dependencies..."
cd frontend && npm install --prefer-offline --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund
cd ..

echo "=== Post-merge setup complete ==="
