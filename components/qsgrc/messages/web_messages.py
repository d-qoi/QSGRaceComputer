from typing import final, override
from qsgrc.messages import BaseMessage

@final
class SSEMessage(BaseMessage):
    leader = "SM"
    subject = "sse.message"
    name = "MSG"

    message: str
    display_time: int

    def __init__(self, message: str, display_time: int):
        self.message = message
        self.display_time = display_time
        value = f"{display_time}|{message}"
        super().__init__(self.name, value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "SSEMessage":
        base = super().unpack(data)
        display_time, message = base.value.split("|", maxsplit=1)

        return cls(message, int(display_time))
