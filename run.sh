#!/usr/bin/env bash
# Script zum einfachen Starten von WayVox

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

if [ -d "venv" ]; then
    venv/bin/python3 main.py "$@"
else
    python3 main.py "$@"
fi
