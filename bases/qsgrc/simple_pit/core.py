from asyncio import Queue, gather, wait_for, create_task
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.staticfiles import StaticFiles
from fastapi_sse import typed_sse_handler
from pydantic import BaseModel

from qsgrc.config import config
from qsgrc.messages import BaseMessage
from qsgrc.messages.alerts import AlertConditionSet, AlertMessage
from qsgrc.messages.obd2 import OBD2Datapoint
from qsgrc.messages.web_messages import SSEMessage as LoRaSSEMessage
from qsgrc.simple_service.lora import LoRaService, LoRaServicePrority


class SSEMessage(BaseModel):
    name: str
    content: str
    timeout: int


class OBD2SSEMessage(SSEMessage):
    units: str


class AlertSSEMessage(SSEMessage):
    value: float
    triggered: bool


sse_messages: Queue[SSEMessage] = Queue()
received_messages: Queue[BaseMessage] = Queue()

lora = LoRaService(received_messages)

running = True


async def handle_incomming_lora():
    while running:
        try:
            packet = await wait_for(received_messages.get(), 1)
            if isinstance(packet, AlertMessage):
                await sse_messages.put(
                    AlertSSEMessage(
                        name=packet.name,
                        content=packet.listen_to,
                        timeout=20,
                        value=packet.val,
                        triggered=packet.triggered,
                    )
                )
            elif isinstance(packet, OBD2Datapoint):
                await sse_messages.put(
                    OBD2SSEMessage(
                        name=packet.name,
                        content=str(packet.val),
                        timeout=0,
                        units=packet.unit,
                    )
                )
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global running

    await lora.run()

    running = True

    tasks = [
        create_task(handle_incomming_lora())
    ]

    yield
    running = False

    await lora.stop()

    try:
        _ = await wait_for(gather(*tasks), 5)
    except TimeoutError:
        for task in tasks:
            _ = task.cancel()


app = FastAPI(lifespan=lifespan)

app.mount("/", StaticFiles(directory=config.www_path, html=True), name="index")


@app.post("/message")
async def send_mesage(msg: SSEMessage) -> None:
    lora_packet = LoRaSSEMessage(
        msg.name,
        msg.content,
        msg.timeout
    )
    await lora.transmit(lora_packet, True, LoRaServicePrority.HIGH)


@app.post("/clear_alert")
async def clear_alert(name: str, command: str) -> None:
    if name not in ("warning", "alert"):
        return status.HTTP_400_BAD_REQUEST
    lora_packet = AlertConditionSet(name, command)
    await lora.transmit


@app.get("/events")
@typed_sse_handler()
async def events():
    while running:
        try:
            message = await wait_for(sse_messages.get(), 1)
            yield message
        except TimeoutError:
            pass
