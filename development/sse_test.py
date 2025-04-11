from asyncio import sleep, Queue, wait_for
import logging

from fastapi import FastAPI, HTTPException, status
from fastapi_sse import sse_handler, typed_sse_handler
from pydantic import BaseModel

log = logging.getLogger("test_server")
log.setLevel(logging.DEBUG)

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
    msg = await msg_queue.get()
    log.info(f"Sending {msg}")
    yield msg


@app.get("/events_longpoll")
async def longpoll():
    try:
        msg = await wait_for(msg_queue.get(), 5)
        return msg
    except TimeoutError:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)
