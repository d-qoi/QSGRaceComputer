from typing import final, override
from qsgrc.messages import BaseMessage

@final
class SSEMessage(BaseMessage):
    leader = "SM"
    subject = "sse.message"

    message: str
    display_time: int

    def __init__(self, name: str, message: str, display_time: int):
        self.name = name
        self.message = message
        self.display_time = display_time
        value = f"{display_time}|{message}"
        super().__init__(self.name, value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "SSEMessage":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        name = match.group(2)
        value = match.group(3)
        display_time, message = value.split("|", maxsplit=1)

        return cls(name, message, int(display_time))
