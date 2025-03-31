from enum import Enum
from multiprocessing import Process, Queue, Event
from typing import Any

from fastapi import FastAPI

from qsgrc.config import config
from qsgrc.log import get_logger
from qsgrc.monitor.obd2 import OBD2Monitor

logger = get_logger("main")

app = FastAPI()




async def obd2_monitor() -> None:
    conn = None
    while conn is None:
        conn = OBD2Monitor()

def main() -> None:
    pass
