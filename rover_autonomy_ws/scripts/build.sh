#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source ./env.sh
.venv/bin/python "$(command -v colcon)" build --symlink-install --packages-select rover_autonomy "$@"
