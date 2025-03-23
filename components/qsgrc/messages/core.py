from re import compile

from pydantic import BaseModel

class BaseMessage:
    leader: str = "0"
    name: str = ""
    value: str= ""

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


class OBD2Datapoint:
    field: str
    value: float

class OBD2Message(BaseModel):
    data: list[OBD2Datapoint]

class SSEMessage(BaseModel):
    event: str
    value: str

class SSECloseStream(SSEMessage):
    pass

def unpack(data: str) -> BaseModel:
    pass
