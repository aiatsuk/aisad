#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.9 or newer is required. Install Python from python.org, then run this again.'
  read -r answer
  exit 1
fi
python3 agent_usage.py --watch 60 --open
