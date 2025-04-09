from asyncio import (
    CancelledError,
    Event,
    Queue,
    Task,
    gather,
    get_running_loop,
    run,
    wait,
    wait_for,
    sleep,
    create_task,
)
from pathlib import Path
import signal
import json
import time
from typing import final

import nats
from nats.aio.msg import Msg
from nats.aio.client import Client as NATS
from nats.aio.subscription import Subscription

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.RYLR896 import RLYR896_MODE, RLYR896_FREQ, RLYR896, errors
from qsgrc.messages import LoRaConfigParams, LoRaConfigPassword, unpack
from qsgrc.messages.core import RequestConfig
from qsgrc.messages.msgpack import MsgPack, ACK
from qsgrc.messages.rlyr896 import LoRaConfigNetwork

logger = get_logger("service.lora")

LORA_PARAMS = LoRaConfigParams(10, 9, 1, 4)
LORA_PASSWORD = LoRaConfigPassword("QSGRC_LORAPASS")

@final
class LoRa_Service:
    max_retries: int = 3
    high_priority_send_limit: int = 5
    resend_interval: float = 5.0
    tasks: list[Task]
    request_config_name: str = "LORA"

    running: bool
    stop_event: Event
    immediate_queue: Queue[str]
    high_priority_queue: Queue[str]
    low_priority_queue: Queue[str]
    incomming_stream: Queue[str]

    processed_data: Queue[str]
    acks_to_send: Queue[int]

    pending_acks: dict[int, tuple[float, int, str, str]]

    msgpack: MsgPack

    def __init__(self) -> None:
        self.tasks = []
        self.stop_event = Event()
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

        self.nc: NATS
        self.lora_con: RLYR896
        self.sub_config: Subscription
        self.sub_transmit: Subscription
        self.sub_config_request: Subscription

        self.stop_event = Event()

    async def __load_saved_config(self) -> None:
        """Load saved configuration from persistent storage"""
        logger.debug("Loading saved configuration.")
        try:
            if config.config_file.exists():
                with open(config.config_file, "r") as f:
                    saved_config = json.load(f)

                    # Apply saved configuration if available
                    if "address" in saved_config:
                        logger.debug(f"Setting address: {saved_config['address']}")
                        await self.lora_con.set_address(saved_config["address"])

                    if "network_id" in saved_config:
                        logger.debug(f"Setting network ID: {saved_config['network_id']}")
                        await self.lora_con.set_network_id(saved_config["network_id"])

                    # Apply other parameters...
                    if "params" in saved_config:
                        logger.debug(f"Setting parameters: {saved_config['params']}")
                        await self.lora_con.set_parameters(
                            saved_config["params"]["spreading_factor"],
                            saved_config["params"]["bandwidth"],
                            saved_config["params"]["coding_rate"],
                            saved_config["params"]["preamble"],
                        )

                    if "password" in saved_config:
                        logger.debug(f"Setting password: {saved_config['password']}")
                        await self.lora_con.set_pass(saved_config["password"])

                    logger.info(f"Loaded saved configuration: {saved_config}")
        except Exception as e:
            logger.error(f"Error loading saved configuration: {e}")

    def __save_config(self) -> None:
        """Save current configuration to persistent storage"""
        logger.debug("Saving current configuration.")
        try:
            config_to_save = {
                "address": self.lora_con.address,
                "network_id": self.lora_con.network_id,
                "params": {
                    "spreading_factor": self.lora_con.spreading_factor,
                    "bandwidth": self.lora_con.bandwidth,
                    "coding_rate": self.lora_con.coding_rate,
                    "preamble": self.lora_con.preamble,
                },
                "password": self.lora_con.password,
            }

            with open(config.config_file, "w") as f:
                json.dump(config_to_save, f)
                logger.info(f"Saved configuration to {str(config.config_file)}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    async def __ack_received(self, tag: int):
        if tag in self.pending_acks:
            logger.info(f"ACK received for {tag}")
            del self.pending_acks[tag]

    async def __send_ack_task(self):
        logger.debug("Starting send ACK task.")
        while self.running:
            try:
                tag = await wait_for(self.acks_to_send.get(), 0.5)
                logger.debug(f"Sending ACK for tag: {tag}")
                await self.immediate_queue.put(str(ACK(tag)))
            except TimeoutError:
                continue
            except CancelledError:
                logger.warning("Ack Task Canceled")
            except Exception as e:
                logger.error(f"Error while trying to send ACK: {e}")

    async def __resend_monitor_task(self):
        logger.debug("Starting resend monitor task.")
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
        logger.debug("Starting transmit task.")
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
                    continue

                try:
                    logger.debug(f"Transmitting packet: {packet}")
                    await self.lora_con.send(config.lora_target_address, packet)
                except errors.ATCommandError as e:
                    logger.error(f"Lora Send Error: {e}")
                await sleep(0.1)
            except CancelledError:
                logger.warning("Transmit Task Canceled")
            except Exception as e:
                logger.error(f"Exception in Transmit Task: {e}")

    async def config_handler(self, msg: Msg):
        params = unpack(msg.data.decode())
        logger.debug(f"Handling config for: {params.leader}")
        if params.leader == LoRaConfigParams.leader:
            create_task(self.config_handler_params(params))
        elif params.leader == LoRaConfigNetwork.leader:
            create_task(self.config_handler_network(params))
        elif params.leader == LoRaConfigPassword.leader:
            create_task(self.config_handler_password(params))
        else:
            logger.warning(f"Unknown config sent to LoRa: {params}")

    async def config_handler_params(self, params: LoRaConfigParams):
        logger.info(f"Setting LoRa parameters: {params}")
        await self.lora_con.set_parameters(
            params.spreading_factor,
            params.bandwidth,
            params.coding_rate,
            params.preamble,
        )
        self.__save_config()

    async def config_handler_network(self, params: LoRaConfigNetwork):
        logger.info(f"Setting LoRa network ID: {params.network_id}, address: {params.address}")
        await self.lora_con.set_network_id(params.network_id)
        await self.lora_con.set_address(params.address)
        self.__save_config()

    async def config_handler_password(self, params: LoRaConfigPassword):
        logger.info(f"Setting LoRa password")
        await self.lora_con.set_pass(params.value)
        self.__save_config()

    async def config_handler_get_config(self, msg: Msg):
        try:
            packet = RequestConfig.unpack(msg.data.decode())
            logger.debug(f"Handling get config for: {packet.name}")
            if packet.name == self.request_config_name:
                params = await self.lora_con.get_parameters()
                data = LoRaConfigParams(**params)
                await self.nc.publish("lora.ack.high", str(data).encode())
        except ValueError as e:
            logger.error(f"Unpack error in get config: {e}")

    async def transmit_handler(self, msg: Msg):
        _, ack, priority = msg.subject.split(".")
        logger.debug(f"Handling transmit for subject: {msg.subject}")
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
        logger.debug("Starting receive handler task.")
        while self.running:
            try:
                data = await wait_for(self.incomming_stream.get(), 0.5)
                self.incomming_stream.task_done()
                message = unpack(data)
                logger.debug(f"Received message, publishing: {message.subject}")
                await self.nc.publish(message.subject, str(message).encode())
            except TimeoutError:
                continue
            except CancelledError:
                logger.warning("Receive Handler Canceled")
            except Exception as e:
                logger.error(f"Error in Receive Task: {e}")

    async def stop(self, *args, **kwargs):
        if not self.running:
            return
        logger.info("Stopping LoRa Service.")
        self.running = False
        try:
            await wait_for(gather(*self.tasks), 5)
        except TimeoutError:
            logger.warning("Timeout waiting for tasks to finish, forcefully cancelling.")
            for task in self.tasks:
                task.cancel()
        self.tasks = []
        await self.sub_transmit.unsubscribe()
        await self.sub_config.unsubscribe()
        await self.sub_config_request.unsubscribe()

        await self.lora_con.stop()
        await self.nc.close()
        await self.stop_event.set()

    async def run(self):
        logger.info("Starting LoRa Service.")
        loop = get_running_loop()
        signals = (signal.SIGTERM, signal.SIGINT)
        for sig in signals:
            loop.add_signal_handler(sig, lambda: loop.create_task(self.stop()))

        self.nc = await nats.connect(str(config.nats_url))
        logger.debug("Connected to NATS.")

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
        await self.__load_saved_config()

        self.running = True

        self.sub_transmit = await self.nc.subscribe(
            "lora.*.*", cb=self.transmit_handler
        )
        self.sub_config = await self.nc.subscribe(
            LoRaConfigParams.subject, cb=self.config_handler
        )
        self.sub_config_request = await self.nc.subscribe(
            RequestConfig.subject, cb=self.config_handler_get_config
        )

        self.tasks.append(create_task(self.__resend_monitor_task()))
        self.tasks.append(create_task(self.__send_ack_task()))
        self.tasks.append(create_task(self.__transmit_task()))
        self.tasks.append(create_task(self.__receive_handler_task()))

        logger.info("LoRa Service tasks started.")
        await self.stop_event.wait()
        logger.info("LoRa Service Finished")


def main():
    service = LoRa_Service()
    run(service.run())
