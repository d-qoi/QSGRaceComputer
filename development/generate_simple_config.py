from qsgrc.messages.obd2 import OBD2Priority, OBD2ConfigMonitor as OBD2Conf
from qsgrc.messages.alerts import AlertConfigMessage, AlertConditions as AC

obd_config_high_priority = ["RPM", "SPEED", "THROTTLE_POS"]

obd_config_low_priority = [
    "OIL_TEMP",
    "INTAKE_TEMP",
    "COOLANT_TEMP",
    "RUN_TIME",
    "FUEL_LEVEL",
    "ENGINE_LOAD",
]

obd_config_high = [
    OBD2Conf(val, True, OBD2Priority.HIGH) for val in obd_config_high_priority
]

obd_config_low = [
    OBD2Conf(val, True, OBD2Priority.LOW) for val in obd_config_low_priority
]

warning = [
    AlertConfigMessage("warning", "RPM", AC.GTE, 4500, False),
    AlertConfigMessage("warning", "SPEED", AC.GTE, 60, False),
]

alert = [
    AlertConfigMessage("alert", "RPM", AC.GTE, 5500, False),
    AlertConfigMessage("alert", "SPEED", AC.GTE, 80, False),
]

with open("simple_config.conf", "w") as f:
    for val in obd_config_low:
        f.write(str(val) + '\n')
    for val in obd_config_high:
        f.write(str(val) + '\n')
    for val in warning:
        f.write(str(val) + '\n')
    for val in alert:
        f.write(str(val) + '\n')
