from random import randint

import serial
ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=1)

def send_data(data):
    ser.write(data.encode()+b"\r\n")
    return ser.readall()

def maybe_get_data():
    if randint(0, 1) == 1:
        return "data"
    raise Exception()

def test():
    try:
        data = maybe_get_data()
    except Exception as e:
        data = ''
        pass
    print(data)
