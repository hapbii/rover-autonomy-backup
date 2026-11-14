import json
import time
from pathlib import Path

from rover_autonomy.config import HardwareConfig
from rover_autonomy.hardware.pi_motors import PiMotors

config = HardwareConfig()
motors = PiMotors(config)
try:
    for _ in range(4):
        motors.apply(0, 0)
        time.sleep(0.05)
    before = {pin: motors.pi.read(pin) for pin in config.standby_pins}
    time.sleep(0.32)
    status, params = motors.pi.script_status(motors.script_id)
    after = {pin: motors.pi.read(pin) for pin in config.standby_pins}
    try:
        motors.apply(0, 0)
    except OSError as error:
        refused = str(error)
    else:
        raise AssertionError("Expired watchdog allowed output")
    assert status == 1 and params[9] == 1 and all(value == 0 for value in after.values())
    report = dict(stby_before=before, stby_after=after, watchdog_status=status,
                  timeout_latched=params[9], output_refused=refused,
                  pwm_nonzero_requested=False, uart_opened=False)
    (Path.home() / "robot_ws/artifacts/pi_pwm_zero_watchdog.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
finally:
    motors.close()
