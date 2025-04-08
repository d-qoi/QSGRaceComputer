from re import Pattern, compile
from typing import final, override


class BaseMessage:
    leader: str = "0"
    subject: str = "base"
    name: str = ""
    value: str = ""

    match_re: Pattern[str] = compile(r"([A-Z0-9]+):([a-zA-Z0-9]+)=(.*)")

    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value

    @classmethod
    def unpack(cls, data: str) -> "BaseMessage":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        return cls(match.group(2), match.group(3))

    @override
    def __str__(self) -> str:
        return f"{self.leader}:{self.name}={self.value}"

    @override
    def __repr__(self) -> str:
        return f"{type(self)} :: {self.__str__()}"

@final
class OBD2Datapoint(BaseMessage):
    leader = "OBD"
    subject = "obd2.data"

@final
class SSEMessage(BaseMessage):
    leader = "SSE"
    subject = "sse"

@final
class RequestConfig(BaseMessage):
    leader = "REQ"
    subject = "config.req"
