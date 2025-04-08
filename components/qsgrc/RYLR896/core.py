"""
AT+ADDRESS:
    set ADDRESS. The ADDRESS is regard as the identification of transmitter or specified receiver.
AT+NETWORKID:
    set the ID of LoRa® network. This is a Group function.
    Only by setting the same NETWORKID can the modules communicate with each other.
    If the ADDRESS of specified receiver is belong to different group, it is not able to communicate with each other.
    The recommend value: 1~15
AT+BAND:
    set the center frequency of wireless band. The transmitter and the receiver are required to use the same frequency to communicate with each other.
AT+PARAMETER: set RF parameters
    <Spreading Factor>, larger is better, but at the cost of transmission time
    <Bandwidth>, smaller is better, but transmission time will be longer
    <Coding Rate>, fastest if setting it as 1
    <Programmed Preamble>, redundency stuff, set higher if needed.
    General Recommended: <3km "AT + PARAMETER = 10,7,1,7", >3km "AT + PARAMETER = 12,4,1,7"
AT+SEND to send data
AT+MODE: 0 for default, 1 to sleep
AT+IRP: baud rate, defaults to 115200
AT+BAND: 915000000 or 915000000
AT+ADDRESS: 0-65535 (will be remembered in EEPROM)
AT+NETWORKID: 0-16 (will be remembered in EEPROM)
AT+CPI: N Set the AES128 password of the network. <Password>: An 32 character long AES password
AT+CRFOP: Set RF Output power, defaults to 15dBm
AT+SEND Send data to the appointment Address
    <Address>0~65535, When the <Address> is 0 it will send data to all address (From 0 to 65535.)
    <Payload Length>Maximum 240bytes
    <Data>ASCII Format

Rec codes:
+ERR
    1 = No enter or \r\n at end of command
    2 = Head of AT command is not 'AT' string
    3 = There is no '=' symbol in the AT command
    4 = Unknown command
   10 = TX is over times
   11 = RX is over times.
   12 = CRC error
   13 = TX data is more than 240 bytes
   15 = unknown error
"""

from asyncio import (
    Queue,
    Lock,
    StreamReader,
    StreamWriter,
    Event,
    Task,
    create_task,
    timeout,
    sleep,
)
from enum import Enum
import re
from typing import Optional
from hashlib import sha256

import serial_asyncio

from qsgrc.RYLR896 import errors
from qsgrc.log import get_logger
from qsgrc.messages.rlyr896 import LoRaConfigParams

CPIN_REGEX = re.compile(r"([0-9a-f]){32}", re.IGNORECASE)

log = get_logger("RLYR896")


class RLYR896_MODE(Enum):
    SLEEP = 1
    ACTIVE = 0


class RLYR896_FREQ(Enum):
    LOW = 868500000
    HIGH = 915000000


class RLYR896(object):
    def __init__(
        self,
        url: str,
        params: LoRaConfigParams,
        message_steam: Queue[str],
        baudrate: int = 115200,
        address: int = 10,
        network_id: int = 3,
        freq: RLYR896_FREQ = RLYR896_FREQ.HIGH,
        password: str = "QSGRC",
    ):
        self.url = url
        self.baudrate = baudrate
        self.rec_task: Optional[Task] = None
        self.rec_event = Event()
        self.received_messages = message_steam
        self.command_response = Queue()
        self.send_lock = Lock()
        self.ready = False

        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None

        self.baudrate = baudrate
        self.address = address
        self.network_id = network_id
        self.freq = freq
        self.spreading_factor = params.spreading_factor
        self.bandwidth = params.bandwidth
        self.coding_rate = params.coding_rate
        self.preamble = params.preamble
        self.password = password

    async def connect(self) -> None:
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.url, baudrate=self.baudrate
        )
        if not self.reader or not self.writer:
            raise errors.ATCommandError("Serial Connection Failed")

    async def stop(self) -> None:
        log.info("Stopping Rec Loop and closing transport.")
        if self.rec_task is None or self.rec_task.done():
            log.info("Task is already done")
            if self.writer:
                self.writer.close()
            return
        try:
            async with timeout(5.0):
                self.rec_event.clear()
                try:
                    await self.ping()
                except errors.RecLoopNotRunning:
                    pass
                except errors.NotReady:
                    pass
                log.info("Stopped Without Timeout")
        except TimeoutError:
            log.warning("Timeout Passed... canceling task.")
            self.rec_task.cancel()
        if self.writer:
            self.writer.close()

    async def start(self) -> None:
        log.info("Starting Rec Loop")
        if self.rec_task is not None and not self.rec_task.done():
            log.debug("Loop is already started")
            return

        self.rec_event.set()
        self.rec_task = create_task(self.__rec_loop())

        log.debug("Started loop")
        while not self.ready:
            await self.ping()
            await sleep(1)
        log.debug("Ping succeeded, setting default values")
        await sleep(0.2)
        await self.set_network_id(self.network_id, force=True)
        await sleep(0.2)
        await self.set_parameters(
            self.spreading_factor, self.bandwidth, self.coding_rate, self.preamble
        )
        await sleep(0.2)
        await self.set_address(self.address, force=True)
        await sleep(0.2)
        await self.set_pass(self.password)
        log.debug("Startup Completed")

    async def ping(self) -> bool:
        try:
            await self.__send("AT", ignore_ready=True)
            self.ready = True
            return True
        except TimeoutError:
            self.ready = False

        return False

    async def soft_reset(self) -> None:
        self.ready = False
        await self.__send("AT+RESET", ignore_ready=True)

    async def send(self, address: int, data: str) -> None:
        if not (0 <= address <= 65535):
            address = 0

        data_length = len(data)

        if not data.isascii():
            raise errors.ATCommandError(message="data must be ASCII")

        if data_length > 240:
            raise errors.TXDataOverflowError()

        await self.__send(f"AT+SEND={address},{data_length},{data}")

    async def set_address(self, address: int, force: bool = False) -> None:
        if not (0 <= address < 65535):
            raise errors.ATCommandError(message="Address Out of Range")

        if address == self.address and not force:
            return

        self.address = address

        await self.__send(f"AT+ADDRESS={address}")

    async def get_address(self) -> int:
        response = await self.__send("AT+ADDRESS?")
        # Response format: +ADDRESS=<value>
        value = int(response.split("=")[1])
        self.address = value
        return value

    async def set_network_id(self, network_id: int, force: bool = False) -> None:
        if not (0 <= network_id <= 16):
            raise errors.ATCommandError(message="Network ID must be between 0 and 16")

        if self.network_id == network_id and not force:
            return

        self.network_id = network_id

        await self.__send(f"AT+NETWORKID={network_id}")

    async def get_network_id(self) -> int:
        response = await self.__send("AT+NETWORKID?")
        # Response format: +NETWORKID=<value>
        value = int(response.split("=")[1])
        self.network_id = value
        return value

    async def set_mode(self, mode: RLYR896_MODE) -> None:
        await self.__send(f"AT+MODE={mode.value}")

    async def set_ipr(self, rate: int) -> None:
        if rate not in [300, 1200, 4800, 9600, 28800, 38400, 57600, 115200]:
            raise errors.ATCommandError(message=f"{rate} is not a valid Baud rate")
        await self.__send(f"AT+IPR={rate}")

    async def get_ipr(self) -> int:
        response = await self.__send("AT+IPR?")
        # Response format: +IPR=<value>
        value = int(response.split("=")[1])
        return value

    async def set_parameters(
        self, spreading_factor: int, bandwidth: int, coding_rate: int, preamble: int
    ) -> None:
        if not (
            5 <= spreading_factor <= 15
            and 0 <= bandwidth <= 9
            and 1 <= coding_rate <= 10
            and 0 <= preamble <= 15
        ):
            raise errors.ATCommandError(
                message=f"Parameters aren't quite right: {spreading_factor}, {bandwidth}, {coding_rate}, {preamble}"
            )
        await self.__send(
            f"AT+PARAMETER={spreading_factor},{bandwidth},{coding_rate},{preamble}"
        )

    async def get_parameters(self) -> dict[str, int]:
        response = await self.__send("AT+PARAMETER?")
        # Response format: +PARAMETER=<sf>,<bw>,<cr>,<pp>
        values = response.split("=")[1].split(",")
        return {
            "spreading_factor": int(values[0]),
            "bandwidth": int(values[1]),
            "coding_rate": int(values[2]),
            "preamble": int(values[3]),
        }

    async def set_freq(self, freq: RLYR896_FREQ) -> None:
        await self.__send(f"AT+BAND={freq.value}")

    async def get_freq(self) -> RLYR896_FREQ | int:
        response = await self.__send("AT+BAND?")
        # Response format: +BAND=<value>
        value = int(response.split("=")[1])
        try:
            return RLYR896_FREQ(value)
        except ValueError:
            return value

    async def set_pass(self, password: str) -> None:
        hashed = sha256(password.encode()).hexdigest()[:32]

        await self.__send(f"AT+CPIN={hashed.upper()}")

    async def get_pass(self) -> str:
        resp = await self.__send("AT+CPIN?")
        return resp

    async def set_power(self, power: int) -> None:
        if not (0 <= power < 20):
            raise errors.ATCommandError(message="Power must be between 0 and 20")

        await self.__send(f"AT+CRFOP={power}")

    async def get_power(self) -> int:
        response = await self.__send("AT+CRFOP?")
        # Response format: +CRFOP=<value>
        value = int(response.split("=")[1])
        return value

    # TODO: Maybe rewrite send/rec to not depend on a queue?
    # Figure out if AT will send multiple errors/
    async def __send(self, data: str, ignore_ready: bool = False) -> str:
        log.debug(f"trying to send {data}")
        if self.writer is None:
            raise BufferError("Writer is not initialized")

        if self.rec_task is None or self.rec_task.done():
            log.error("Rec loop is not running, failing send")
            raise errors.RecLoopNotRunning

        if not self.ready and not ignore_ready:
            log.error("Not ready to receive")
            raise errors.NotReady

        async with self.send_lock:
            log.debug(f"Lock acquired, ready, sending {data}")

            # Empty command response, no clutter.
            while not self.command_response.empty():
                resp = await self.command_response.get()
                log.debug(f"emptying command response: {resp}")

            log.debug(f"Writing: {data.encode()+b'\r\n'}")
            self.writer.write(data.encode() + b"\r\n")
            await self.writer.drain()
            try:
                async with timeout(5.0):
                    data = await self.command_response.get()
            except TimeoutError:
                raise TimeoutError

            log.debug(f"Response received: {data}")
            if data.startswith("+ERR"):
                err_num = int(data.split("=")[1])
                raise errors.get_error_by_code(err_num)
            return data

    async def __rec_loop(self):
        while self.rec_event.is_set():
            if self.reader is None:
                await sleep(1)
                continue
            data = ""
            try:
                data = await self.reader.readline()
            except Exception as e:
                log.error(f"read line error: {e}")
                continue
            if not data:
                continue
            try:
                data = data.decode().strip()
            except UnicodeDecodeError as e:
                log.error(f"Error in rec loop decode: {e}")
                continue
            if data.startswith("+ERR"):
                log.error(f"Error: {data}")
                await self.command_response.put(data)
            elif data.startswith("+READY"):
                log.info("Device is ready")
                self.ready = True
            elif data.startswith("+RCV"):
                log.debug(f"Received message: {data}")
                await self.received_messages.put(data)
            else:
                await self.command_response.put(data)
        self.ready = False
