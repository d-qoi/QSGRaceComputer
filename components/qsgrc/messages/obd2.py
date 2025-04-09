from enum import Enum
from typing import final, override

from qsgrc.messages.core import BaseMessage
from qsgrc.monitor.obd2.command_mapping import COMMAND_MAP, SHORTENED_MAP


class OBD2Priority(Enum):
    IMMEDIATE = 0
    HIGH = 1
    LOW = 2
    REMOVE = 3


@final
class OBD2Datapoint(BaseMessage):
    leader = "OBD"
    subject = "obd2.data"

    listen_for: str
    val: float
    unit: str

    def __init__(self, listen_for, val, unit):
        self.name = listen_for
        self.listen_for = listen_for
        self.val = val
        self.unit = unit

        self.value = f"{self.val}|{self.unit}"
        super().__init__(self.name, self.value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "OBD2Datapoint":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        value = match.group(3)
        val, unit = value.split("|")
        return cls(cls.name, val, unit)

class OBD2Config(BaseMessage):
    subject: str = "config.obd2"


@final
class OBD2ConfigMonitor(OBD2Config):
    leader = "COBD1"
    name = "MONCONF"

    priority: OBD2Priority
    listen_to: str
    send_to_pit: bool

    def __init__(self, listen_to: str, send_to_pit: bool, priority: OBD2Priority):
        self.priority = priority
        self.listen_to = listen_to
        self.send_to_pit = send_to_pit

        shortened_cmd = COMMAND_MAP.get(listen_to)
        if not shortened_cmd:
            raise ValueError(f"Unknown Command: {listen_to}")
        self.value = f"{shortened_cmd}.{priority.value}.{int(send_to_pit)}"
        super().__init__(self.name, self.value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "OBD2ConfigMonitor":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        value = match.group(3)
        name = match.group(2)
        if name != cls.name:
            raise ValueError(f"Name Mismatch: {cls.name} != {name}")
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid Param Format, expecting 3 parts: {parts}")

        return cls(
            SHORTENED_MAP[parts[0]], bool(int(parts[1])), OBD2Priority(int(parts[2]))
        )
