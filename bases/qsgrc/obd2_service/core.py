from asyncio import Task, create_task, gather, run, wait_for

import nats
from nats.aio.msg import Msg
from nats.aio.client import Client as NATS
from nats.aio.subscription import Subscription

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.monitor.obd2.core import OBD2Monitor

logger = get_logger("service.obd2")

class OBD2_Service:
    def __init__(self):
        self.obd: OBD2Monitor = OBD2Monitor()
        self.nc: NATS

        self.running: bool = False
        self.tasks: list[Task] = []
        self.subscriptions: list[Subscription] = []

    async def __send_obd2(self):
        while self.running:
            pass

    async def stop(self):
        if not self.running:
            return

        self.running = False

        try:
            await wait_for(gather(*self.tasks), 5)
        except TimeoutError:
            for task in self.tasks:
                task.cancel()
        finally:
            self.tasks = []

        for sub in self.subscriptions:
            await sub.unsubscribe()
        await self.nc.close()

        await self.obd.stop()
        self.obd.close()


    async def run(self):
        self.running = True
        self.nc = await nats.connect(str(config.nats_url))
        self.obd.start()
        self.tasks.append(create_task(self.__send_obd2()))

def main():
    service = OBD2_Service()
    run(service.run())
