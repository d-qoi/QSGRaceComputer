from asyncio import (
    CancelledError,
    Queue,
    Task,
    get_running_loop,
    run,
    wait_for,
    sleep,
    create_task,
)
import signal
import time
from typing import Dict

import nats
from nats.aio.msg import Msg
from nats.aio.client import Client as NATS

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.RYLR896 import RLYR896_MODE, RLYR896_FREQ, RLYR896, errors
from qsgrc.messages import LoRaConfigParams, LoRaConfigPassword, unpack
from qsgrc.messages.core import RequestConfig
from qsgrc.messages.msgpack import MsgPack, ACK

logger = get_logger("service.lora")

LORA_PARAMS = LoRaConfigParams(10, 9, 1, 4)
LORA_PASSWORD = LoRaConfigPassword("QSGRC_LORAPASS")


class LoRa_Service:
    max_retries: int = 3
    high_priority_send_limit: int = 5
    resend_interval: float = 5.0
    tasks: list[Task]
    request_config: str = "LORA"

    running: bool
    immediate_queue: Queue[str]
    high_priority_queue: Queue[str]
    low_priority_queue: Queue[str]
    incomming_stream: Queue[str]

    processed_data: Queue[str]
    acks_to_send: Queue[int]

    pending_acks: Dict[int, tuple[float, int, str, str]]

    msgpack: MsgPack
    lora_con: RLYR896
    nc: NATS

    def __init__(self) -> None:
        self.tasks = []

        self.running = False
        self.immediate_queue = Queue()
        self.high_priority_queue = Queue()
        self.low_priority_queue = Queue()
        self.incomming_stream = Queue()

        self.processed_data = Queue()
        self.acks_to_send = Queue()

        self.pending_acks = {}

        self.msgpack = MsgPack(
            self.incomming_stream,
            self.processed_data,
            self.acks_to_send,
            self.__ack_received,
        )

    async def __ack_received(self, tag: int):
        if tag in self.pending_acks:
            logger.info(f"ACK received for {tag}")
            del self.pending_acks[tag]

    async def __send_ack_task(self):
        while self.running:
            try:
                tag = await wait_for(self.acks_to_send.get(), 0.5)
                await self.immediate_queue.put(str(ACK(tag)))
            except TimeoutError:
                continue
            except CancelledError:
                logger.warning("Ack Task Canceled")
            except Exception as e:
                logger.error(f"Error while trying to send ACK: {e}")

    async def __resend_monitor_task(self):
        while self.running:
            try:
                now = time.monotonic()

                for tag in list(self.pending_acks.keys()):
                    (expiry, attempt, queue, data) = self.pending_acks[tag]
                    if now < expiry:
                        continue
                    if attempt >= self.max_retries:
                        logger.warning(
                            f"Failed to receive ACK for tag: {tag} after {self.max_retries} attempts"
                        )
                        del self.pending_acks[tag]
                        continue
                    logger.info(f"{tag} not acked, resending")
                    new_attempts = attempt + 1
                    new_expiry = now + self.resend_interval
                    if queue == "immediate":
                        tag = await self.msgpack.split_messages_to_queue(
                            data, self.immediate_queue, True, tag=tag
                        )
                    else:
                        tag = await self.msgpack.split_messages_to_queue(
                            data, self.high_priority_queue, True, tag=tag
                        )
                    self.pending_acks[tag] = (new_expiry, new_attempts, queue, data)

                await sleep(0.5)
            except CancelledError:
                logger.warning("Resend Monitor Task Canceled")
            except Exception as e:
                logger.error(f"Exception in Resend Monitor: {e}")

    async def __transmit_task(self):
        high_priority_count = 0
        while self.running:
            try:
                packet = ""
                if self.immediate_queue.qsize() > 0:
                    logger.debug("Sending From Immediate Queue")
                    packet = await self.immediate_queue.get()
                if (
                    packet == ""
                    and high_priority_count < self.high_priority_send_limit
                    and self.high_priority_queue.qsize() > 0
                ):
                    high_priority_count += 1
                    packet = await self.high_priority_queue.get()
                else:
                    high_priority_count = 0

                if packet == "" and self.low_priority_queue.qsize() > 0:
                    packet = await self.low_priority_queue.get()
                    high_priority_count = 0

                if packet == "":
                    await sleep(0.25)
                else:
                    try:
                        await self.lora_con.send(config.lora_target_address, packet)
                    except errors.ATCommandError as e:
                        logger.error(f"Lora Send Error: {e}")
                    await sleep(0.1)
            except CancelledError:
                logger.warning("Transmit Task Canceled")
            except Exception as e:
                logger.error(f"Exception in Transmit Task: {e}")

    async def config_handler_params(self, msg: Msg):
        params = LoRaConfigParams.unpack(msg.data.decode())
        await self.lora_con.set_parameters(
            params.spreading_factor,
            params.bandwidth,
            params.coding_rate,
            params.preamble,
        )

    async def config_handler_password(self, msg: Msg):
        params = LoRaConfigPassword.unpack(msg.data.decode())
        await self.lora_con.set_pass(params.value)

    async def config_handler_get_config(self, msg: Msg):
        try:
            packet = RequestConfig.unpack(msg.data.decode())
            if packet.name == "LORA":
                params = await self.lora_con.get_parameters()
                data = LoRaConfigParams(**params)
                await self.nc.publish("lora.ack.high", str(data).encode())
        except ValueError as e:
            logger.error(f"Unpack error in get config: {e}")

    async def transmit_handler(self, msg: Msg):
        _, ack, priority = msg.subject.split(".")
        ack_needed = ack == "ack"
        tag = 0
        if priority == "immediate":
            tag = await self.msgpack.split_messages_to_queue(
                msg.data.decode(), self.immediate_queue, ack_needed
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
            expiry_time = time.monotonic() + self.resend_interval
            self.pending_acks[tag] = (expiry_time, 0, priority, msg.data.decode())
            logger.info(f"Tracking message ({tag}) for ack")

    async def __receive_handler_task(self):
        while self.running:
            try:
                data = await wait_for(self.incomming_stream.get(), 0.5)
                message = unpack(data)
                await self.nc.publish(message.leader, str(message).encode())
            except TimeoutError:
                continue
            except CancelledError:
                logger.warning("Receive Handler Canceled")
            except Exception as e:
                logger.error(f"Error in Receive Task: {e}")

    async def stop(self):
        pass

    async def run(self):
        loop = get_running_loop()
        signals = (signal.SIGTERM, signal.SIGINT)
        for sig in signals:
            loop.add_signal_handler(sig, lambda: create_task(self.stop()))

        self.nc = await nats.connect(str(config.nats_url))

        self.lora_con = RLYR896(
            str(config.lora_url),
            LORA_PARAMS,
            self.incomming_stream,
            address=config.lora_address,
            network_id=config.lora_network_id,
            password=LORA_PASSWORD.value,
        )

        await self.lora_con.connect()
        await self.lora_con.start()

        self.running = True

        self.sub_transmit = await self.nc.subscribe(
            "lora.*.*", cb=self.transmit_handler
        )
        self.sub_config_params = await self.nc.subscribe(
            LoRaConfigParams.leader, cb=self.config_handler_params
        )
        self.sub_config_pass = await self.nc.subscribe(
            LoRaConfigPassword.leader, cb=self.config_handler_password
        )
        self.sub_request_config = await self.nc.subscribe(
            RequestConfig.leader, cb=self.config_handler_get_config
        )

        self.tasks.append(create_task(self.__resend_monitor_task()))
        self.tasks.append(create_task(self.__send_ack_task()))
        self.tasks.append(create_task(self.__transmit_task()))
        self.tasks.append(create_task(self.__receive_handler_task()))


def main():
    service = LoRa_Service()
    run(service.run())
