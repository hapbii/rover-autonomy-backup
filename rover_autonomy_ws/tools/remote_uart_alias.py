import json
import subprocess
from pathlib import Path

rule = Path("/etc/udev/rules.d/99-rover-uart.rules")
desired = 'SUBSYSTEM=="tty", KERNEL=="ttyAMA0", SYMLINK+="serial0", GROUP="dialout", MODE="0660"\n'
if rule.exists() and rule.read_text() != desired:
    raise RuntimeError("Existing UART rule differs; manual review required")
rule.write_text(desired)
subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
subprocess.run(["udevadm", "trigger", "--subsystem-match=tty", "--sysname-match=ttyAMA0"], check=True)
subprocess.run(["udevadm", "settle"], check=True)
alias = Path("/dev/serial0")
if not alias.exists() or alias.resolve() != Path("/dev/ttyAMA0"):
    raise RuntimeError("Primary UART alias was not created")
print(json.dumps({"serial0": str(alias.resolve()), "rule": str(rule), "uart_opened": False}))
