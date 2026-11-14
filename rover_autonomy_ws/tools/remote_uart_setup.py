"""Back up boot configuration, reserve Pi 4 primary UART and release motor GPIO."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

if os.geteuid() != 0:
    raise RuntimeError("Root is required to update boot settings")
model = Path("/proc/device-tree/model").read_text().rstrip("\0")
if "Raspberry Pi 4" not in model:
    raise RuntimeError(f"Unexpected board {model}")
boot = Path("/boot/firmware")
config = boot / "config.txt"
cmdline = boot / "cmdline.txt"
original = {p.name: p.read_bytes() for p in (config, cmdline)}
backup = boot / ("rover_uart_backup_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
backup.mkdir()
for p in (config, cmdline):
    shutil.copy2(p, backup / p.name)
    if (backup / p.name).read_bytes() != original[p.name]:
        raise RuntimeError("Boot backup mismatch")
text = original["config.txt"].decode()
for key in ("audio", "i2c_arm", "spi"):
    text, count = re.subn(rf"(?m)^\s*dtparam={key}=on\s*$", f"dtparam={key}=off", text)
    if not count and f"dtparam={key}=off" not in text:
        raise RuntimeError(f"Unexpected {key} configuration; manual review required")
text += "\n# Rover GPIO UART, 2026-11-13; sensor data only\n[all]\nenable_uart=1\ndtoverlay=disable-bt\n"
args = original["cmdline.txt"].decode().split()
args = [value for value in args if not re.match(r"console=(serial0|ttyAMA\d+|ttyS\d+)(,|$)", value)]
if not any(value.startswith("root=") for value in args):
    raise RuntimeError("Missing root option in kernel command line")
config.write_text(text)
cmdline.write_text(" ".join(args) + "\n")
services = {}
for unit in ("serial-getty@serial0.service", "serial-getty@ttyS0.service", "serial-getty@ttyAMA0.service"):
    result = subprocess.run(["systemctl", "disable", "--now", unit], capture_output=True, text=True)
    services[unit] = {"exit": result.returncode, "stderr": result.stderr[-1000:]}
proof = {"backup": str(backup), "model": model, "reboot_required": True,
         "expected_uart": "/dev/serial0 -> /dev/ttyAMA0",
         "bluetooth_uart_reassigned": True, "motor_gpio_peripherals_disabled": ["i2c_arm", "spi", "audio"],
         "uart_opened": False, "motor_output_enabled": False, "services": services,
         "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (config, cmdline)}}
(backup / "changes.json").write_text(json.dumps(proof, indent=2))
print(json.dumps(proof, indent=2), flush=True)
