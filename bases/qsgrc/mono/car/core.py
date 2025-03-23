from fastapi import FastAPI

from qsgrc.config import config
from qsgrc.log import get_logger

logger = get_logger("main")

app = FastAPI()

def main() -> None:
    pass
