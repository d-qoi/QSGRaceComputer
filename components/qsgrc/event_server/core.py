from asyncio import Queue, Event

from fastapi_sse import sse_handler
from fastapi import APIRouter

from qsgrc.messages.core import SSECloseStream, SSEMessage
from qsgrc.log import get_logger


logger = get_logger("event_server")

event_queue: Queue[SSEMessage] = Queue()
event_server_continue = Event()


router = APIRouter()


@router.get("/")
@sse_handler()
async def event_server():
    logger.info("Starting SSE Event Stream")
    while not event_server_continue.is_set():
        message = await event_queue.get()
        if isinstance(message, SSECloseStream):
            event_server_continue.set()
            logger.debug("Closing Stream")
            continue
        logger.debug(f"Sending Message: {type(message)}: {message.event}:{message.value}")
        yield message

async def add_message(message: SSEMessage) -> None:
    logger.debug(f"Received Message: {type(message)}: {message.event}:{message.value}")
    await event_queue.put(message)
