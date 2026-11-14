import serial
import time
for baud in (57600, 38400, 19200, 115200):
    with serial.Serial('COM8', baud, timeout=0.12) as connection:
        connection.dtr = False
        connection.rts = False
        time.sleep(0.15)
        connection.dtr = True
        connection.rts = True
        time.sleep(0.05)
        connection.reset_input_buffer()
        synced = False
        for index in range(12):
            connection.write(b'\x30\x20')
            response = connection.read(2)
            if response == b'\x14\x10':
                synced = True
                connection.write(b'\x75\x20')
                print('signature', connection.read(5).hex(), flush=True)
                break
        print('baud', baud, 'synced', synced, flush=True)
    if synced:
        break
