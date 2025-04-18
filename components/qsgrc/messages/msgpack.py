from re import compile
from asyncio import Queue, Task, create_task, gather, wait_for
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from qsgrc.log import get_logger
from qsgrc.messages.core import BaseMessage

PACKET_REGEX = compile(r"^(([0-9]+)\/([0-9]+))?\|([0-9]+)\|(.+)$")

logger = get_logger("messages.msgpack")


class ACK:
    def __init__(self, tag: int):
        self.tag = tag

    def __str__(self):
        return f"ACK:{self.tag}"

    @classmethod
    def unpack(cls, data: str) -> "ACK":
        _, tag = data.split(":")
        return ACK(int(tag))


class Packet:
    count: int
    total: int
    tag: int
    data: str

    def __init__(self, count: int, total: int, tag: int, data: str):
        self.count = count
        self.total = total
        self.data = data
        self.tag = tag

    def __str__(self):
        if self.count == 0:
            return f"|{self.tag}|{self.data}"
        return f"{self.count}/{self.total}|{self.tag}|{self.data}"

    @classmethod
    def unpack(cls, data: str) -> "Packet":
        match = PACKET_REGEX.fullmatch(data)
        if not match:
            raise ValueError(f"Data did not match regex: {data}")
        if match.group(1):
            count = int(match.group(2))
            total = int(match.group(3))
        else:
            count = 0
            total = 0
        tag = int(match.group(4))
        data = match.group(5)
        return cls(count, total, tag, data)


# Use a callback type for better type hints
AckCallbackType = Callable[[int], Awaitable[None]]


class MsgPack:
    # Tag: received, total, data
    buffers: dict[int, tuple[int, int, list[str]] | None]
    in_stream: Queue[str]
    processed_data: Queue[str]
    ack_stream: Queue[int]
    ack_callback: AckCallbackType

    ack_threshold: int = 50
    max_tag: int = 100
    split_length: int = 220

    def __init__(
        self,
        in_stream: Queue[str],
        processed_data: Queue[str],
        ack_stream: Queue[int],
        ack_callback: AckCallbackType,
    ) -> None:
        logger.info("Initializing MsgPack message handler")
        self.buffers = {}
        self.in_stream = in_stream
        self.processed_data = processed_data
        self.ack_stream = ack_stream
        self.ack_callback = ack_callback
        self.running: bool = False
        self.nack_tag: int = 1
        self.ack_tag: int = self.ack_threshold
        self.__tasks: list[Task] = []
        logger.debug(
            f"MsgPack configured with split_length={self.split_length}, ack_threshold={self.ack_threshold}"
        )

    async def __process_ack(self, msg: str) -> None:
        logger.debug(f"Processing ACK message: {msg}")
        try:
            ack = ACK.unpack(msg)
            logger.info(f"Received ACK for tag {ack.tag}")
            await self.ack_callback(ack.tag)
        except Exception as e:
            logger.error(f"Error processing ACK message '{msg}': {e}")

    async def __process_packet(self, msg: str) -> None:
        # tag < 50: no ack needed
        # tag >= 50: ack needed.
        # If count = 0, single packet
        try:
            data = Packet.unpack(msg)

            if data.count == 0:
                logger.debug(f"Processing single packet with tag {data.tag}")

                if data.tag in self.buffers:
                    logger.warning(f"Clearing existing buffer for tag {data.tag}")
                    del self.buffers[data.tag]

                await self.processed_data.put(data.data)

                if data.tag >= self.ack_threshold:
                    await self.ack_stream.put(data.tag)
                return

            # Multi-packet handling
            logger.debug(f"Processing fragment {data.count}/{data.total} with tag: {data.tag}")

            if data.tag not in self.buffers or self.buffers[data.tag][1] != data.total:
                self.buffers[data.tag] = (0, data.total, [""] * data.total)
                logger.info(f"New buffer for tag: {data.tag}, expecting {data.total} fragments")

            received, total, data_buffer = self.buffers[data.tag]
            if -0 < data.count <= total:
                data_buffer[data.count - 1] = data.data
                received = sum(1 for packet in data_buffer if packet)

                if received == total:
                    completed_message = "".join(data_buffer)
                    logger.info(f"Message with tag ({data.tag}) completed ({len(completed_message)} bytes)")
                    await self.processed_data.put(completed_message)
                    del self.buffers[data.tag]
                else:
                    self.buffers[data.tag] = (received, total, data_buffer)
                    logger.debug(f"Buffer for tag {data.tag}: {received}/{total}, expecting {data.total} fragments")

            else:
                logger.warning(f"Invalid fragment {data.count} for tag {data.tag}")

            if data.tag >= self.ack_threshold:
                await self.ack_stream.put(data.tag)
        except ValueError as e:
            logger.error(f"Error parsing packet '{msg}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing packet: '{msg}': {e}", exc_info=True)

    async def __process_inbound_packet(self, msg: str) -> None:
        logger.debug(
            f"Processing inbound message: {msg[:15]}{'...' if len(msg) > 15 else ''}"
        )
        if msg.startswith("ACK:"):
            await self.__process_ack(msg)
        else:
            await self.__process_packet(msg)

    async def __loop(self):
        logger.info("Message processing loop started")
        try:
            while self.running:
                logger.debug("Waiting for incoming message")

                try:
                    packet = await wait_for(self.in_stream.get(), 0.5)
                except TimeoutError:
                    continue

                logger.debug(f"Received message from queue, length={len(packet)}")

                try:
                    await self.__process_inbound_packet(packet)
                except Exception as e:
                    logger.error(f"Error in message processing: {e}")
                finally:
                    self.in_stream.task_done()
                    logger.debug("Finished processing message")
        except Exception as e:
            logger.error(f"Fatal error in message processing loop: {e}")
            self.running = False

        logger.info("Message processing loop ended")

    def __get_tag(self, ack: bool):
        tag = self.ack_tag if ack else self.nack_tag

        if ack:
            logger.debug(f"Using ACK tag {tag}")
            self.ack_tag += 1
            if self.ack_tag >= self.max_tag:
                self.ack_tag = self.ack_threshold
                logger.debug(f"ACK tag cycle completed, reset to {self.ack_threshold}")
        else:
            logger.debug(f"Using non-ACK tag {tag}")
            self.nack_tag += 1
            if self.nack_tag >= self.ack_threshold:
                self.nack_tag = 1
                logger.debug(f"Non-ACK tag cycle completed, reset to 1")

        return tag

    async def start(self):
        logger.info("Starting MsgPack message handler")
        self.running = True
        self.__tasks = [create_task(self.__loop())]
        logger.debug("Message processing task created")

    async def stop(self):
        logger.info("Stopping MsgPack message handler")
        self.running = False

        if len(self.__tasks) == 0:
            logger.warning("No tasks to stop")
            return

        try:
            logger.debug("Waiting for tasks to complete")
            _ = await wait_for(gather(*self.__tasks), 3)
            logger.info("All tasks stopped gracefully")
        except TimeoutError:
            logger.warning("Timeout waiting for tasks to stop, canceling forcefully")
            for task in self.__tasks:
                task.cancel()
        finally:
            self.__tasks = []

    async def split_messages_to_queue(
            self, data: str | BaseMessage, stream: Queue[str], ack_needed: bool, tag: int | None = None
    ) -> int:
        message_type = type(data).__name__
        logger.info(
            f"Sending {message_type} message, ACK {'required' if ack_needed else 'not required'}"
        )
        if tag is None:
            tag = self.__get_tag(ack_needed)
        data_string = str(data)
        data_length = len(data_string)

        logger.debug(
            f"Message length: {data_length} bytes, max packet size: {self.split_length}"
        )

        if data_length <= self.split_length:
            logger.debug(f"Message fits in a single packet, sending with tag {tag}")
            await stream.put(str(Packet(0, 0, tag, data_string)))
            return tag

        # Split message into multiple packets
        logger.info(f"Splitting message ({data_length} bytes) into multiple packets")

        packets: list[str] = []
        packet_0 = data_string[: self.split_length]
        rest = data_string[self.split_length :]

        packets.append(packet_0)

        fragment_count = 1
        while len(rest) > 0:
            next_packet = rest[: self.split_length]
            rest = rest[self.split_length :]
            packets.append(next_packet)
            fragment_count += 1
            logger.debug(
                f"Created fragment {fragment_count}, {len(rest)} bytes remaining"
            )

        total = len(packets)
        logger.info(f"Message split into {total} fragments with tag {tag}")

        for i, packet in enumerate(packets):
            # count is 1 based
            packet_obj = Packet(i + 1, total, tag, packet)
            logger.debug(
                f"Sending fragment {i+1}/{total} with tag {tag}, length={len(packet)}"
            )
            await stream.put(str(packet_obj))

        logger.debug(f"All {total} fragments for {tag} queued for sending")
        return tag
