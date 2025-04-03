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
            raise ValueError("Data did not match regex: {data}")
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
    buffers: Dict[int, Optional[Tuple[int, int, List[str]]]]
    in_stream: Queue[str]
    ack_stream: Queue[int]
    ack_callback: AckCallbackType

    ack_threshold = 50
    max_tag = 100
    split_length = 220

    def __init__(
        self,
        in_stream: Queue,
        default_out_stream: Queue,
        ack_stream: Queue,
        ack_callback: AckCallbackType,
    ) -> None:
        self.buffers = {}
        self.in_stream = in_stream
        self.out_stream = default_out_stream
        self.ack_stream = ack_stream
        self.ack_callback = ack_callback
        self.running = False
        self.nack_tag = 1
        self.ack_tag = self.ack_threshold
        self.__tasks: list[Task] = []

    async def __process_ack(self, msg: str) -> None:
        try:
            ack = ACK.unpack(msg)
            await self.ack_callback(ack.tag)
        except Exception as e:
            logger.error(f"Error processing ACK: {e}")

    async def __process_packet(self, msg: str) -> None:
        # tag < 50: no ack needed
        # tag >= 50: ack needed.
        # If count = 0, single packet
        try:
            data = Packet.unpack(msg)
        except ValueError as e:
            logger.error(e)
            return
        # Data is single packet
        buffered_data = self.buffers.get(data.tag, None)
        # Single Message
        if data.count == 0:
            if buffered_data is not None:
                logger.warning(
                    "Received Message Outside of Buffer, clearing and continuing"
                )
                self.buffers.pop(data.tag)
            await self.out_stream.put(data.data)
            if data.tag >= 50:
                await self.ack_stream.put(data.tag)
            return
        # Split message
        # Initialize buffered data if needed.
        if buffered_data is None:
            buffered_data = (0, data.total, [""] * data.total)

        received, total, data_buffer = buffered_data
        received += 1

        # Count starts at 1, not 0, offsetting by 1
        data_buffer[data.count - 1] = data.data

        # Check to see if all packets have been received
        # In case of out of order received
        if total == data.count or received == total:
            if all([len(packet) for packet in data_buffer]):
                await self.out_stream.put("".join(data_buffer))
                self.buffers.pop(data.tag)
        else:
            # Save new data in buffer
            self.buffers[data.tag] = (received, total, data_buffer)

        if data.tag >= 50:
            await self.ack_stream.put(data.tag)
        logger.debug(f"Done processing packet {data.tag}")

    async def __process_inbound_packet(self, msg: str) -> None:
        if msg.startswith("ACK:"):
            await self.__process_ack(msg)
        else:
            await self.__process_packet(msg)

    async def __loop(self):
        while self.running:
            packet = await self.in_stream.get()
            await self.__process_inbound_packet(packet)
            self.in_stream.task_done()

    def __get_tag(self, ack: bool):
        tag = self.ack_tag if ack else self.nack_tag
        if ack:
            self.ack_tag += 1
            if self.ack_tag >= self.max_tag:
                self.ack_tag = self.ack_threshold
        else:
            self.nack_tag += 1
            if self.nack_tag >= self.ack_threshold:
                self.nack_tag = 1
        return tag

    async def start(self):
        self.running = True
        self.__tasks = [create_task(self.__loop())]

    async def stop(self):
        self.running = False
        try:
            await wait_for(gather(*self.__tasks), 3)
        except TimeoutError:
            logger.warning("Timeout waiting for main loop to stop, canceling")
            for task in self.__tasks:
                task.cancel()

    async def split_messages_to_queue(
        self, data: BaseMessage, stream: Queue[str], ack_needed: bool = True
    ):
        tag = self.__get_tag(ack_needed)
        data_string = str(data)
        if len(data_string) <= self.split_length:
            await stream.put(str(Packet(0, 0, tag, data_string)))
            return

        packets = []
        packet_0 = data_string[: self.split_length]
        rest = data_string[self.split_length :]

        packets.append(packet_0)
        while len(rest) > 0:
            next_packet = rest[: self.split_length]
            rest = rest[self.split_length :]
            packets.append(next_packet)

        total = len(packets)
        for i, packet in enumerate(packets):
            # count is 1 based
            await stream.put(str(Packet(i + 1, total, tag, packet)))

    async def send_message(self, data: BaseMessage, ack_needed: bool = True):
        """Send a message through the default out_stream"""
        await self.split_messages_to_queue(data, self.out_stream, ack_needed)
