from asyncio import (
    CancelledError,
    Queue,
    Task,
    gather,
    get_running_loop,
    wait_for,
    sleep,
    create_task,
)
from enum import Enum
import signal
import time
from typing import final

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.RYLR896 import RLYR896, errors
from qsgrc.messages import BaseMessage, LoRaConfigParams, LoRaConfigPassword, unpack
from qsgrc.messages.msgpack import MsgPack, ACK

logger = get_logger("service.lora")

LORA_PARAMS = LoRaConfigParams(10, 9, 4, 6)


class LoRaServicePrority(Enum):
    LOW = 0
    HIGH = 1
    IMMEDIATE = 2


@final
class LoRaService:
    max_retries: int = 3
    high_priority_send_limit: int = 5
    resend_interval: float = 5.0
    tasks: list[Task[None]]
    request_config_name: str = "LORA"

    running: bool

    immediate_queue: Queue[str]
    high_priority_queue: Queue[str]
    low_priority_queue: Queue[str]

    unprocessed_messages_queue: Queue[str]
    processed_data_queue: Queue[str]

    acks_to_send: Queue[int]
    pending_acks: dict[int, tuple[float, int, LoRaServicePrority, str]]

    msgpack: MsgPack

    def __init__(self, received_message: Queue[BaseMessage]) -> None:
        self.tasks = []

        self.running = False

        self.immediate_queue = Queue()
        self.high_priority_queue = Queue()
        self.low_priority_queue = Queue()

        self.unprocessed_messages_queue = Queue()
        self.processed_data_queue = Queue()

        self.received_messages: Queue[BaseMessage] = received_message

        self.acks_to_send = Queue()
        self.pending_acks = {}

        self.msgpack = MsgPack(
            self.unprocessed_messages_queue,
            self.processed_data_queue,
            self.acks_to_send,
            self.__ack_received,
        )

        self.lora_con: RLYR896 = RLYR896(
            str(config.lora_url),
            LORA_PARAMS,
            self.unprocessed_messages_queue,
            address=config.lora_address,
            network_id=config.lora_network_id,
        )

    async def __ack_received(self, tag: int):
        '''
        Handle ack being received, and cleaning up the pending acks dict.
        '''
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
        '''
        Will cyckle through the pending messages in the pending_acks list,
        Will send the message again at high priority if no ack has been received.
        Will try 3 times to get the message through.
        '''
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
                    if queue == LoRaServicePrority.IMMEDIATE:
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
        """
        Cycles through queues and will send in order of priority
        """
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

    async def __receive_handler_task(self):
        """
        Takes messages that have been recombined into one data string, and unpacks
        that into received_messages.
        """
        logger.debug("Starting receive handler task.")
        while self.running:
            try:
                data = await wait_for(self.processed_data_queue.get(), 0.5)
                self.processed_data_queue.task_done()
                message = unpack(data)
                logger.debug(f"Received message: {message}")
                await self.received_messages.put(message)
            except TimeoutError:
                continue
            except CancelledError:
                logger.warning("Receive Handler Canceled")
            except Exception as e:
                logger.error(f"Error in Receive Task: {e}")

    async def transmit(
        self,
        data: BaseMessage,
        ack: bool,
        priority: LoRaServicePrority,
    ):
        tag = 0
        logger.debug(f"Transmitting {"ack needed" if ack else "no ack needed "}")
        logger.debug(f"Trasmitting packet with {priority}")
        logger.debug(f"{data}")
        if priority == LoRaServicePrority.IMMEDIATE:
            tag = await self.msgpack.split_messages_to_queue(
                str(data), self.immediate_queue, ack
            )
        elif priority == LoRaServicePrority.HIGH:
            tag = await self.msgpack.split_messages_to_queue(
                str(data), self.high_priority_queue, ack
            )
        elif priority == LoRaServicePrority.LOW:
            tag = await self.msgpack.split_messages_to_queue(
                str(data), self.low_priority_queue, ack
            )
        if tag > self.msgpack.ack_threshold:
            expiry_time = time.monotonic() + self.resend_interval
            self.pending_acks[tag] = (expiry_time, 0, priority, str(data))
            logger.info(f"Tracking message ({tag}) for ack")

    async def stop(self):
        if not self.running:
            return
        logger.info("Stopping LoRa Service.")
        self.running = False
        try:
            _ = await wait_for(gather(*self.tasks), 5)
        except TimeoutError:
            logger.warning(
                "Timeout waiting for tasks to finish, forcefully cancelling."
            )
            for task in self.tasks:
                _ = task.cancel()
        self.tasks = []

        await self.lora_con.stop()

    async def run(self):
        logger.info("Starting LoRa Service.")
        loop = get_running_loop()
        signals = (signal.SIGTERM, signal.SIGINT)
        for sig in signals:
            loop.add_signal_handler(sig, lambda: loop.create_task(self.stop()))

        await self.lora_con.connect()
        await self.lora_con.start()

        self.running = True

        self.tasks.append(create_task(self.__resend_monitor_task()))
        self.tasks.append(create_task(self.__send_ack_task()))
        self.tasks.append(create_task(self.__transmit_task()))
        self.tasks.append(create_task(self.__receive_handler_task()))
