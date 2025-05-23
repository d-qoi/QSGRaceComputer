from asyncio import Queue, gather, wait_for, create_task
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from qsgrc.alerts import MonitorAlerts
from qsgrc.config import config
from qsgrc.log import get_logger
from qsgrc.messages import BaseMessage, unpack
from qsgrc.messages.alerts import (
    AlertConfigMessage,
    AlertMessage,
    AlertConditionSet,
)
from qsgrc.messages.obd2 import OBD2ConfigMonitor, OBD2Datapoint
from qsgrc.messages.web_messages import SSEMessage as loraSSEMessage
from qsgrc.simple_service.lora import LoRaService, LoRaServicePrority
from qsgrc.simple_service.obd import OBD2Service


log = get_logger("simple_car")


class SSEMessage(BaseModel):
    name: str
    content: str
    timeout: int


class AlertSSEMessage(SSEMessage):
    value: float
    triggered: bool


obd2_stream: Queue[OBD2Datapoint] = Queue()
received_messages: Queue[BaseMessage] = Queue()
sse_messages: Queue[SSEMessage] = Queue()
alert_messages: Queue[AlertMessage] = Queue()
warning_feed: Queue[tuple[str, float]] = Queue()
alert_feed: Queue[tuple[str, float]] = Queue()

obd2 = OBD2Service(obd2_stream)
lora = LoRaService(received_messages)
warnings = MonitorAlerts("warning", alert_messages, warning_feed)
alerts = MonitorAlerts("alert", alert_messages, alert_feed)
running = True


def load_config():
    with open(config.config_file, "r") as f:
        for line in f:
            try:
                msg = unpack(line.strip())
                if isinstance(msg, OBD2ConfigMonitor):
                    obd2.update_polling_monitor(msg)
                elif isinstance(msg, AlertConfigMessage):
                    if msg.name == warnings.name:
                        warnings.add_rule(
                            msg.listen_to, msg.condition, msg.threshold, msg.hold
                        )
                    elif msg.name == alerts.name:
                        alerts.add_rule(
                            msg.listen_to, msg.condition, msg.threshold, msg.hold
                        )
                else:
                    log.warning(f"Unknown data in config: {msg}")
            except ValueError as e:
                log.error(f"Error in unpacking config: {line}")
                log.error(f"{e}")


async def redirect_obd2_stream():
    while running:
        try:
            packet = await wait_for(obd2_stream.get(), 1)
            await warning_feed.put((packet.listen_for, packet.val))
            await alert_feed.put((packet.listen_for, packet.val))
            await lora.transmit(packet, False, LoRaServicePrority.LOW)
        except TimeoutError:
            pass


async def redirect_alert_stream():
    while running:
        try:
            packet = await wait_for(alert_messages.get(), 1)
            if packet.name == warnings.name:
                await lora.transmit(packet, True, LoRaServicePrority.HIGH)
            else:
                await lora.transmit(packet, True, LoRaServicePrority.IMMEDIATE)
            await sse_messages.put(
                AlertSSEMessage(
                    name=packet.name,
                    content=packet.listen_to,
                    timeout=30,
                    triggered=packet.triggered,
                    value=packet.val,
                )
            )
        except TimeoutError:
            pass


async def handle_incomming_lora():
    while running:
        try:
            packet = await wait_for(received_messages.get(), 1)
            if isinstance(packet, AlertConditionSet):
                if packet.name == warnings.name:
                    await warnings.clear_alert_condition(packet.value)
                elif packet.name == alerts.name:
                    await alerts.clear_alert_condition(packet.value)
            elif isinstance(packet, loraSSEMessage):
                await sse_messages.put(
                    SSEMessage(
                        name=packet.name,
                        content=packet.message,
                        timeout=packet.display_time,
                    )
                )
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global running
    load_config()
    await lora.run()
    await warnings.start()
    await alerts.start()
    await obd2.run()

    running = True

    tasks = [
        create_task(handle_incomming_lora()),
        create_task(redirect_alert_stream()),
        create_task(redirect_obd2_stream()),
    ]

    yield

    running = False

    await obd2.stop()
    await warnings.stop()
    await alerts.stop()
    await lora.stop()

    try:
        _ = await wait_for(gather(*tasks), 5)
    except TimeoutError:
        for task in tasks:
            _ = task.cancel()


app = FastAPI(lifespan=lifespan)

app.mount("/", StaticFiles(directory=config.www_path, html=True), name="index")


@app.get("/events")
async def longpoll():
    try:
        msg = await wait_for(sse_messages.get(), 5)
        return msg
    except TimeoutError:
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)
