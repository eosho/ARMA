#!/bin/bash
# Helper script to run ARMA CLI with the correct virtual environment

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment and run arma
source "$SCRIPT_DIR/.venv/bin/activate"
"$SCRIPT_DIR/.venv/bin/arma" "$@"
