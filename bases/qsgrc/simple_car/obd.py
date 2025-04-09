from asyncio import Event, Task, Queue, create_task, gather,  wait_for

from obd import OBDResponse

from qsgrc.config import config
from qsgrc.log import get_logger
from qsgrc.messages import RequestConfig
from qsgrc.messages.obd2 import OBD2ConfigMonitor, OBD2Datapoint, OBD2Priority
from qsgrc.monitor.obd2 import OBD2Monitor

logger = get_logger("service.obd2")

class OBD2Service:
    def __init__(self, obd2_stream: Queue[OBD2Datapoint]):
        self.obd: OBD2Monitor = OBD2Monitor(portstr=config.obd2_url)

        self.config: dict[str, tuple[OBD2Priority, bool]]

        self.obd2_stream: Queue[OBD2Datapoint]

        self.running: bool = False
        self.tasks: set[Task[None]] = set()

    async def __task_publish_obd2(self):
        while self.running:
            try:
                listen_for, value = await wait_for(self.obd.responses(), 0.5)
                await self.obd2_stream.put(OBD2Datapoint(listen_for, value.value, value.unit))
            except TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error caught while trying to publish to obd2.data: {e}")

    def update_polling_monitor(self, data: OBD2ConfigMonitor):
        if data.priority == OBD2Priority.HIGH:
            _ = self.obd.add_high_priority(data.listen_to)
        elif data.priority == OBD2Priority.LOW:
            _ = self.obd.add_low_priority(data.listen_to)
        else:
            (
                self.obd.remove_high_priority(data.listen_to)
                or self.obd.remove_low_priority(data.listen_to)
            )

    async def stop(self):
        if not self.running:
            return

        self.running = False

        try:
            _ = await wait_for(gather(*self.tasks), 5)
        except TimeoutError:
            for task in self.tasks:
                _ = task.cancel()
        finally:
            self.tasks = set()

        await self.obd.stop()
        self.obd.close()

    async def run(self):
        self.running = True
        await self.obd.start()
        self.tasks.add(create_task(self.__task_publish_obd2()))

