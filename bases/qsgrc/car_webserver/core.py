from asyncio import Queue
from contextlib import asynccontextmanager
from fastapi import FastAPI

import nats
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg
from nats.aio.subscription import Subscription

from qsgrc.config import config
from qsgrc.log import get_logger
from qsgrc.messages.alerts import AlertMessage


logger = get_logger("service.web")

app = FastAPI()
nc: NATS

async def handle_alert(msg: Msg):
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    nc = await nats.connect(str(config.nats_url))
    alert_subscription: Subscription = await nc.subscribe(AlertMessage.subject, cb=handle_alert)
    messages_subscription: Subscription = await nc.subscribe(

    yield

    await alert_subscription.unsubscribe()
    await nc.close()
