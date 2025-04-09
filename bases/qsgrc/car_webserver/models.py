from pydantic import BaseModel

class Alert(BaseModel):
    name: str
    command: str
    value: float

class Message(BaseModel):
    message: str
    dislay_time: int
