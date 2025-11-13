#!/usr/bin/env bash
set -e
ROOT_DIR=$(cd "$(dirname "$0")"; pwd -P)
python -m venv .venv
. .venv/Scripts/activate; pip install -r requirements.txt
