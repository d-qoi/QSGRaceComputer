from enum import Enum
from re import compile
from typing import Any

from pydantic import BaseModel

class MonitorAlertConditions(Enum):
    GT = 1
    GTE = 2
    LT = 3
    LTE = 4
    EQ = 5


class BaseMessage:
    leader: str = "0"
    name: str = ""
    value: Any = None

    match_re = compile(r"([A-Z0-9]+):([a-zA-Z0-9]+)=(.*)")

    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value

    @classmethod
    def unpack(cls, data: str):
        match = cls.match_re.fullmatch(data)
        if not match:
            raise TypeError
        elif match.group(1) != cls.leader:
            raise TypeError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        return cls(match.group(2), match.group(3))

    def __str__(self) -> str:
        return f"{self.leader}:{self.name}={self.value}"

    def __repr__(self) -> str:
        return f"{type(self)} :: {self.__str__()}"


class OBD2Datapoint(BaseMessage):
    leader = "OBD2dp"
    field: str
    value: float

    def __init__(self, field, value) -> None:
        self.field = field
        self.value = value

    def __str__(self) -> str:
        return f"{self.field}={self.value}"

    @classmethod
    def unpack(cls, data) -> "OBD2Datapoint":
        field, value = data.split("=")
        return cls(field, value)


class OBD2Message(BaseMessage):
    leader = "OBD2"
    value: list[OBD2Datapoint]

    @classmethod
    def unpack(cls, data):
        pass


class SSEMessage(BaseModel):
    event: str
    value: str


class SSECloseStream(SSEMessage):
    pass

