from asyncio import Queue
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from qsgrc.config import config
from qsgrc.messages import BaseMessage

class SSEMessage(BaseModel):
    name: str
    content: str
    timeout: int

class OBD2SSEMessage(SSEMessage):
    pass

class AlertSSEMessage(SSEMessage):
    value: float
    triggered: bool


sse_messages: Queue[SSEMessage] = Queue()
received_messages: Queue[BaseMessage] = Queue()

lora = LoRaService(received_messages)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)

app.mount('/', StaticFiles(directory=config.www_path, html=True), name="index")
