#!/usr/bin/env bash
set -eo pipefail
cd /home/takyeji/robot_ws
trap 'setup_status=$?; printf "%s\n" "$setup_status" > artifacts/pi_setup.exit' EXIT
date -Is
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-pi.txt pytest psutil
source ./env.sh
python scripts/doctor.py --require-ros
bash scripts/build.sh
source install/setup.bash
python -m pytest -q --junitxml=artifacts/pi_test_report.xml
ros2 pkg executables rover_autonomy
date -Is
