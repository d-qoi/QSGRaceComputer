from asyncio import Event, Task, Queue, create_task, wait_for, gather, run

import nats
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg
from nats.aio.subscription import Subscription


from qsgrc.alerts import MonitorAlerts
from qsgrc.config import config
from qsgrc.log import get_logger
from qsgrc.messages import RequestConfig
from qsgrc.messages.alerts import AlertConditions, AlertConfigMessage, AlertMessage
from qsgrc.messages.obd2 import OBD2Datapoint


logger = get_logger("service.alerts")


class AlertService:
    def __init__(self) -> None:
        self.running: bool = False
        self.stop_event: Event = Event()

        self.tasks: set[Task[None]] = set()

        self.out_stream: Queue[AlertMessage] = Queue()
        self.in_stream: Queue[tuple[str, float]] = Queue()

        self.alert_monitors: dict[str, MonitorAlerts] = {}

        self.nc: NATS
        self.obd2_subscription: Subscription
        self.sub_config: Subscription
        self.sub_config_request: Subscription

    async def __task_publish_lora(self):
        while self.running:
            try:
                packet = await wait_for(self.out_stream.get(), 1)
                await self.nc.publish(packet.subject, str(packet).encode())
            except TimeoutError:
                pass

    async def handle_obd2_feed(self, msg: Msg):
        try:
            packet = OBD2Datapoint.unpack(msg.data.decode())
            await self.in_stream.put((packet.listen_for, packet.val))
        except ValueError as e:
            logger.error(f"Value Error in unpacking OBD2 data: {e}")

    async def handle_config(self, msg: Msg):
        try:
            packet = AlertConfigMessage.unpack(msg.data.decode())
            if packet.name not in self.alert_monitors:
                self.alert_monitors[packet.name] = MonitorAlerts(
                    packet.name, self.out_stream, self.in_stream
                )
                await self.alert_monitors[packet.name].start()

            if packet.condition == AlertConditions.REMOVE:
                self.alert_monitors[packet.name].remove_rule(packet.listen_to)
            else:
                self.alert_monitors[packet.name].add_rule(
                    packet.listen_to, packet.condition, packet.threshold, packet.hold
                )
        except ValueError as e:
            logger.error(f"Error in adding rule: {e}")

    async def handle_config_request(self, msg: Msg):
        try:
            packet = RequestConfig.unpack(msg.data.decode())
            if packet.name != "ALERTS":
                return
            for key in list(self.alert_monitors.keys()):
                for listen_for, rule in list(self.alert_monitors[key].rules.items()):
                    cond, hold, threshold = rule
                    to_send = AlertConfigMessage(key, listen_for, cond, threshold, hold)
                    await self.nc.publish("lora.ack.high", str(to_send).encode())
        except ValueError as e:
            logger.error(f"Unpack error in get config: {e}")

    async def stop(self):
        self.running = False

        await self.obd2_subscription.unsubscribe()
        await self.sub_config.unsubscribe()
        await self.sub_config_request.unsubscribe()

        try:
            await wait_for(gather(*self.tasks), 5)
        except TimeoutError:
            for task in self.tasks:
                task.cancel()

        await self.nc.close()
        self.stop_event.set()

    async def run(self):
        self.nc = await nats.connect(str(config.nats_url))

        self.obd2_subscription = await self.nc.subscribe(
            OBD2Datapoint.subject, cb=self.handle_obd2_feed
        )
        self.sub_config = await self.nc.subscribe(
            AlertConfigMessage.subject, cb=self.handle_config
        )
        self.sub_config_request = await self.nc.subscribe(
            RequestConfig.subject, cb=self.handle_config_request
        )

        task = create_task(self.__task_publish_lora())
        self.tasks.add(task)

        self.stop_event.clear()
        await self.stop_event.wait()

def main():
    service = AlertService()
    run(service.run())
