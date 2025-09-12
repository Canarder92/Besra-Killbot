#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$(cd "$(dirname "$0")/.."; pwd)"
cd "$PYTHONPATH"
python -m src.bot
