from asyncio import Task, create_task, gather, run, wait_for, sleep
from audioop import add

import nats
from nats.aio.msg import Msg
from nats.aio.client import Client as NATS
from nats.aio.subscription import Subscription
from obd import OBDResponse

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.messages.core import RequestConfig
from qsgrc.messages.obd2 import OBD2ConfigMonitor, OBD2Datapoint, OBD2Priority
from qsgrc.monitor.obd2 import OBD2Monitor

logger = get_logger("service.obd2")


class OBD2_Service:
    def __init__(self):
        self.obd: OBD2Monitor = OBD2Monitor()
        self.nc: NATS

        self.config: dict[str, tuple[OBD2Priority, bool]]

        self.running: bool = False
        self.tasks: set[Task[None]] = set()
        self.sub_config: Subscription
        self.sub_config_request: Subscription

    async def __task_publish_obd2(self):
        while self.running:
            try:
                listen_for, value = await wait_for(self.obd.responses(), 0.5)
                msg = OBD2Datapoint(listen_for, value.value, value.unit)
                await self.nc.publish(OBD2Datapoint.subject, str(msg).encode())
            except TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error caught while trying to publish to obd2.data: {e}")

    def __task_publish_lora(self, cmd: str, resp: OBDResponse):
        packet = OBD2Datapoint(cmd, resp.value, resp.unit)
        task = create_task(self.nc.publish("lora.nack.low", str(packet).encode()))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def dump_config_to_lora(self):
        config_packets: list[OBD2ConfigMonitor] = []
        for cmd, callback in self.obd.high_priority.items():
            config_packets.append(
                OBD2ConfigMonitor(cmd, callback is not None, OBD2Priority.HIGH)
            )
        for cmd, callback in self.obd.low_priority.items():
            config_packets.append(
                OBD2ConfigMonitor(cmd, callback is not None, OBD2Priority.LOW)
            )

        for packet in config_packets:
            await self.nc.publish("lora.ack.high", str(packet).encode())

    async def __config_req_handler(self, msg: Msg):
        task = create_task(self.dump_config_to_lora())
        task.add_done_callback(self.tasks.discard)
        self.tasks.add(task)

    def update_polling_monitor(self, data: OBD2ConfigMonitor):
        callback = self.__task_publish_lora if data.send_to_pit else None
        if data.priority == OBD2Priority.HIGH:
            _ = self.obd.add_high_priority(data.listen_to, callback=callback)
        elif data.priority == OBD2Priority.LOW:
            _ = self.obd.add_low_priority(data.listen_to, callback=callback)
        else:
            (
                self.obd.remove_high_priority(data.listen_to)
                or self.obd.remove_low_priority(data.listen_to)
            )

    async def handle_oneshot(self, data: OBD2ConfigMonitor):
        resp = await self.obd.oneshot(data.listen_to)
        packet = OBD2Datapoint(data.listen_to, resp.value, resp.unit)
        await self.nc.publish("lora.ack.high", str(resp).encode())

    async def __config_handler(self, msg: Msg):
        try:
            data = OBD2ConfigMonitor.unpack(msg.data.decode())
            if data.priority in (
                OBD2Priority.HIGH,
                OBD2Priority.LOW,
                OBD2Priority.REMOVE,
            ):
                self.update_polling_monitor(data)
            elif data.priority == OBD2Priority.IMMEDIATE:
                task = create_task(self.handle_oneshot(data))
                task.add_done_callback(self.tasks.discard)
                self.tasks.add(task)
        except:
            pass

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

        await self.sub_config.unsubscribe()
        await self.sub_config_request.unsubscribe()
        await self.nc.close()

        await self.obd.stop()
        self.obd.close()

    async def run(self):
        self.running = True
        self.nc = await nats.connect(str(config.nats_url))
        await self.obd.start()

        self.sub_config = await self.nc.subscribe(
            OBD2ConfigMonitor.subject, cb=self.__config_handler
        )
        self.sub_config_request = await self.nc.subscribe(
            RequestConfig.subject, cb=self.__config_req_handler
        )

        self.tasks.add(create_task(self.__task_publish_obd2()))
        


def main():
    service = OBD2_Service()
    run(service.run())
