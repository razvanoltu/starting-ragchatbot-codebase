#!/usr/bin/env bash
# Frontend quality checks — runs Prettier format check on all frontend files.
# Usage:
#   ./scripts/check-frontend.sh          # check only (exits non-zero on violations)
#   ./scripts/check-frontend.sh --fix    # auto-format in place

set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")/../frontend" && pwd)"

if ! command -v npx &>/dev/null; then
    echo "Error: npx is not installed. Install Node.js (https://nodejs.org) and run 'npm install' inside the frontend/ directory."
    exit 1
fi

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
    echo "Installing frontend dev dependencies..."
    npm install
fi

if [ "${1:-}" = "--fix" ]; then
    echo "Formatting frontend files..."
    npx prettier --write "**/*.{js,css,html}"
    echo "Done. All files formatted."
else
    echo "Checking frontend formatting..."
    npx prettier --check "**/*.{js,css,html}"
    echo "All files are correctly formatted."
fi
