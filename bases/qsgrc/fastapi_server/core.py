from fastapi import FastAPI
from fastapi_sse import sse_handler

from qsgrc.log import get_logger
from qsgrc.config import config

logger = get_logger("server")
app = FastAPI()

@app.get("/events")
@sse_handler()
async def event_stream():
    pass
