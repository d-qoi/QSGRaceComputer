from asyncio import Queue, run, wait_for
import time
from typing import Dict

import nats
from nats.aio.msg import Msg

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.RYLR896 import RLYR896_MODE, RLYR896_FREQ, RLYR896, errors
from qsgrc.messages import LoRaConfigParams, LoRaConfigPassword, 
from qsgrc.messages.msgpack import MsgPack, ACK

logger = get_logger("service.lora")

LORA_PARAMS = LoRaConfigParams(10, 9, 1, 4)
LORA_PASSWORD = LoRaConfigPassword("QSGRC_LORAPASS")


class LoRa_Service:
    def __init__(self) -> None:
        self.running: bool = False
        self.immediate_stream: Queue[str] = Queue()
        self.high_priority_queue: Queue[str] = Queue()
        self.low_priority_queue: Queue[str] = Queue()
        self.incomming_stream: Queue[str] = Queue()

        self.processed_data: Queue[str] = Queue()
        self.acks_to_send: Queue[int] = Queue()

        self.acks_needed: Dict[int, tuple[int, str, str]] = {}

        self.msgpack = MsgPack(
            self.incomming_stream,
            self.processed_data,
            self.acks_to_send,
            self.__ack_received,
        )

    async def __ack_received(self, tag: int):
        pass

    async def __send_ack_task(self):
        while self.running:
            try:
                tag = await wait_for(self.acks_to_send.get(), 0.5)
                await self.immediate_stream.put(str(ACK(tag)))
            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error while trying to send ACK: {e}")

    async def __resend_monitor_task(self):
        while self.running:
            try:
                now = time.monotonic()

    async def transmit_handler(self, msg: Msg):
        _, ack, priority = msg.subject.split(".")
        ack_needed = ack == "ack"
        tag = 0
        if priority == "immediate":
            tag = await self.msgpack.split_messages_to_queue(
                msg.data.decode(), self.immediate_stream, ack_needed
            )
        elif priority == "high":
            tag = await self.msgpack.split_messages_to_queue(
                msg.data.decode(), self.high_priority_queue, ack_needed
            )
        elif priority == "low":
            tag = await self.msgpack.split_messages_to_queue(
                msg.data.decode(), self.low_priority_queue, ack_needed
            )
        if tag > self.msgpack.ack_threshold:
            self.acks_needed

    async def receive_handler(self):
        pass

    async def run(self):
        self.nc = await nats.connect(str(config.nats_url))

        self.lora_con = RLYR896(
            str(config.lora_url),
            LORA_PARAMS,
            self.incomming_stream,
            address=config.lora_address,
            network_id=config.lora_network_id,
            password=LORA_PASSWORD.value,
        )

        self.transmit = await self.nc.subscribe("lora.*.*", cb=self.transmit_handler)


def main():
    service = LoRa_Service()
    run(service.run())
