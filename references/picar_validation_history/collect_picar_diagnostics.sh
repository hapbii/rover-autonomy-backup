#!/bin/bash
# Diagnostic collection only: no package installation, service changes or motion.
# Run on the Raspberry Pi: bash collect_picar_diagnostics.sh
set -u
umask 077
task_report_dir="${PWD}/picar-diagnostics-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$task_report_dir"
task_report_log="$task_report_dir/diagnostics.txt"
exec > >(tee "$task_report_log") 2>&1
run_readonly() {
  printf '\n$'
  printf ' %q' "$@"
  printf '\n'
  "$@" || printf '[command unavailable, inaccessible or nonzero]\n'
}
run_readonly date --iso-8601=seconds
run_readonly uname -a
run_readonly cat /etc/os-release
run_readonly cat /proc/device-tree/model
run_readonly python3 --version
run_readonly command -v python3
run_readonly locale
run_readonly locale -a
run_readonly systemctl status Adeept_Robot.service --no-pager -l
run_readonly systemctl cat Adeept_Robot.service
run_readonly journalctl -u Adeept_Robot.service -b --no-pager -n 150
run_readonly systemctl status wifi-hotspot-manager.service --no-pager -l
run_readonly ss -ltnp
run_readonly ip -brief address
if command -v vcgencmd >/dev/null 2>&1; then
  run_readonly vcgencmd get_throttled
fi
if command -v raspi-config >/dev/null 2>&1; then
  run_readonly raspi-config nonint get_i2c
  run_readonly raspi-config nonint get_spi
fi
run_readonly python3 - <<'PY'
from pathlib import Path
import hashlib, importlib.metadata, importlib.util, json, sys
print('interpreter:',sys.executable)
for name in ['websockets','flask','flask-cors','adafruit-blinka',
             'adafruit-circuitpython-pca9685','adafruit-circuitpython-motor',
             'gpiozero','numpy','opencv-python','opencv-python-headless','picamera2']:
    try:print('distribution:',name,importlib.metadata.version(name))
    except importlib.metadata.PackageNotFoundError:print('distribution:',name,'metadata absent')
for name in ['websockets','board','busio','adafruit_pca9685','adafruit_motor',
             'gpiozero','smbus','spidev','rpi_ws281x','cv2','picamera2','libcamera']:
    try:
        spec=importlib.util.find_spec(name)
        print('module:',name,None if spec is None else spec.origin)
    except Exception as e:print('module:',name,type(e).__name__,str(e))
print('devices:',[str(p) for pattern in ['i2c-*','spidev*','gpiochip*'] for p in Path('/dev').glob(pattern)])
for rel in ['web/WebServer.py','web/move.py','web/RPIservo.py','web/functions.py','setup.py']:
    path=Path.home()/'adeept_picar-b2'/rel
    print('source SHA256:',str(path),hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else 'not found at default path')
PY
printf '\nSaved: %s\n' "$task_report_log"
printf 'If journal access was denied, collect those same journal/status commands with sudo.\n'
printf 'No actuator commands or installation commands were executed.\n'
