from asyncio import sleep, Queue

from fastapi import FastAPI
from fastapi_sse import sse_handler, typed_sse_handler
from pydantic import BaseModel


class SSEMessage(BaseModel):
    name: str
    content: str
    timeout: int


class AlertSSEMessage(SSEMessage):
    value: float
    triggered: bool


app = FastAPI()
msg_queue: Queue[SSEMessage] = Queue()


@app.post("/message")
async def send_message(msg: SSEMessage) -> int:
    await msg_queue.put(msg)
    return msg_queue.qsize()


@app.post("/alert")
async def send_alert(msg: AlertSSEMessage) -> int:
    await msg_queue.put(msg)
    return msg_queue.qsize()


@app.get("/events")
@typed_sse_handler()
async def index():
    for i in range(10):
        yield Message(msg=f"index: {i}")
        await sleep(2)
