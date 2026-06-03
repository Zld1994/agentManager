#!/usr/bin/env bash
# agentManager installer for Linux/macOS
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/install.py "$@"
