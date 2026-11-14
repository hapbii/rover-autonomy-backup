import json,pathlib,shutil,subprocess,sys,tempfile,time
import serial
from serial.tools import list_ports
root=pathlib.Path.cwd()
sys.path.insert(0,str(root/'scripts'))
sys.path.insert(0,str(root/'src/rover_autonomy'))
from setup_arduino import arduino_environment
from rover_autonomy.hardware.sensor_protocol import READY,parse_telemetry
port=next(p for p in list_ports.comports() if p.device=='COM8')
assert (port.vid,port.pid)==(0x2341,0x0043)
with tempfile.TemporaryDirectory(prefix='rover_ra2_upload_') as folder:
    image=pathlib.Path(folder)/'ra2.hex'
    shutil.copy2(root/'artifacts/firmware/rover_sensors.ino.hex',image)
    result=subprocess.run([str(root/'tools/arduino-cli.exe'),'upload','--fqbn','arduino:avr:uno','--port','COM8','--input-file',str(image),'--verify'],env=arduino_environment(),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
    (root/'artifacts/uno_ra2_upload_attempt.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    print('upload_exit',result.returncode,flush=True)
    print(result.stdout+result.stderr,flush=True)
    result.check_returncode()
with serial.Serial('COM8',115200,timeout=0.2) as link:
    time.sleep(2)
    link.reset_input_buffer()
    link.write(b'HELLO\n')
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        text=link.readline().decode('ascii',errors='replace').strip()
        if text:
            print(text,flush=True)
        if text==READY:
            link.write(b'CFG 1 1 1 1\n')
        elif text.startswith('S '):
            parse_telemetry(text)
            break
    else:
        raise RuntimeError('RA2 handshake missing')
