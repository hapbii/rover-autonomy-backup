"""Back up the explicitly selected Uno and upload/identify RA2 over laptop USB."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import serial
from serial.tools import list_ports

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src/rover_autonomy"))
from rover_autonomy.hardware.sensor_protocol import READY, parse_telemetry

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
port = "COM8"
device = next((p for p in list_ports.comports() if p.device == port), None)
if device is None or (device.vid, device.pid) != (0x2341, 0x0043):
    raise RuntimeError("Expected Arduino Uno on COM8 is not present")
stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
destination = root / "artifacts" / ("uno_uart_setup_" + stamp)
destination.mkdir()
tool = Path.home() / "AppData/Local/Temp/rover_avrdude_6_3_official/avrdude"
prefix = [str(tool / "bin/avrdude.exe"), "-C", str(tool / "etc/avrdude.conf"),
          "-p", "atmega328p", "-c", "arduino", "-P", port, "-b", "115200"]
with tempfile.TemporaryDirectory(prefix="rover_uno_uart_") as temporary:
    stage = Path(temporary)
    backup = subprocess.run(prefix + ["-U", "flash:r:flash_before.hex:i", "-U", "eeprom:r:eeprom_before.hex:i"],
                            cwd=stage, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    (destination / "backup.log").write_text(backup.stdout + backup.stderr, encoding="utf-8")
    print("backup_exit", backup.returncode, flush=True)
    backup.check_returncode()
    for name in ("flash_before.hex", "eeprom_before.hex"):
        shutil.copy2(stage / name, destination / name)
    image = root / "artifacts/firmware/rover_sensors.ino.hex"
    shutil.copy2(image, stage / "ra2.hex")
    upload = subprocess.run(prefix + ["-D", "-U", "flash:w:ra2.hex:i"], cwd=stage, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=45)
    (destination / "upload.log").write_text(upload.stdout + upload.stderr, encoding="utf-8")
    print("upload_exit", upload.returncode, flush=True)
    upload.check_returncode()
report = {"port": port, "uploaded_at": datetime.now(timezone.utc).isoformat(),
          "backup": str(destination), "hex_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
          "flash_verified_by_avrdude": True, "motor_output": False}
lines = []
with serial.Serial(port, 115200, timeout=0.1, write_timeout=0.2) as connection:
    time.sleep(2.0)
    connection.reset_input_buffer()
    connection.write(b"HELLO\n")
    identified = False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        line = connection.readline().decode("ascii", errors="replace").strip()
        if not line:
            continue
        lines.append(line)
        if line == READY:
            identified = True
            connection.write(b"CFG 1 1 1 1\n")
        elif identified and line.startswith("S "):
            value = parse_telemetry(line)
            report.update(identified=True, telemetry_sequence=value.sequence,
                          range_mm=value.range_mm, ir_raw_mask=value.ir_mask, counts=value.counts)
            break
    else:
        raise RuntimeError("RA2 upload succeeded but sensor handshake did not complete")
(destination / "serial_identification.log").write_text("\n".join(lines), encoding="utf-8")
(destination / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(root / "artifacts/uno_uart_latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
