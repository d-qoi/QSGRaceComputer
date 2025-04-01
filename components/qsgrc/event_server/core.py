from asyncio import Queue, Event

from fastapi_sse import sse_handler
from fastapi import APIRouter

from qsgrc.messages.core import SSEMessage
from qsgrc.log import get_logger


logger = get_logger("event_server")

event_queue: Queue[SSEMessage] = Queue()
event_server_continue = Event()


router = APIRouter()


@router.get("/")
@sse_handler(emit_type=True)
async def event_server():
    logger.info("Starting SSE Event Stream")
    while not event_server_continue.is_set():
        message = await event_queue.get()
        logger.debug(f"Sending Message: {type(message)}: {message.name}:{message.value}")
        yield message

async def add_message(message: SSEMessage) -> None:
    logger.debug(f"Received Message: {type(message)}: {message.name}:{message.value}")
    await event_queue.put(message)
