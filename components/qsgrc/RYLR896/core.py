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

from asyncio import Queue, Lock, StreamReader, StreamWriter, Event, create_task, timeout
from enum import Enum
import re

import serial_asyncio

from qsgrc.RYLR896 import errors
from qsgrc.log import get_logger

CPIN_REGEX = re.compile(r"([0-9a-f]){32}", re.IGNORECASE)

log = get_logger(__name__)

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
        baudrate: int = 115200,
        address: int = 10,
        network_id: int = 3,
    ):
        self.url = url
        self.baudrate = baudrate
        self.rec_task = None
        self.rec_event = Event()
        self.message_queue = Queue()
        self.command_response = Queue()
        self.send_lock = Lock()
        self.ready = False

        self.reader: StreamReader = None
        self.writer: StreamWriter = None

        self.baudrate = baudrate
        self.address = address
        self.network_id = network_id

    async def connect(self):
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.url, baudrate=self.baudrate
        )

    async def stop(self):
        try:
            async with timeout(5.0):
                self.rec_event.clear()
                try:
                    await self.ping()
                except errors.RecLoopNotRunning:
                    pass
                except errors.NotReady:
                    pass
        except TimeoutError:
            if self.rec_task:
                self.rec_task.cancel()

    async def start(self):
        self.rec_event.set()
        self.rec_task = create_task(self.__rec_loop())
        await self.ping()
        await self.set_ipr(self.baudrate)
        await self.set_address(self.address)
        await self.set_network_id(self.network_id)

    async def ping(self):
        try:
            await self.__send("AT", ignore_ready=True)
            self.ready = True
        except TimeoutError:
            self.ready = False

    async def soft_reset(self):
        await self.__send("AT+RESET")
        self.ready = False

    async def send(self, data: str, address: int=0):
        if not (0 <= address <= 65535 ):
            address = 0

        data_length = len(data)

        if not data.isascii:
            raise errors.ATCommandError(message="data must be ASCII")

        if data_length > 240:
            raise errors.TXDataOverflowError()

        await self.__send(f"AT+SEND={address},{data_length},{data}")

    async def set_address(self, address: int):
        if not (0 <= address < 65535):
            raise errors.ATCommandError(message="Address Out of Range")

        await self.__send(f"AT+ADDRESS={address}")

    async def get_address(self):
        response = await self.__send("AT+ADDRESS?")
        # Response format: +ADDRESS=<value>
        value = int(response.split("=")[1])
        return value

    async def set_network_id(self, network_id: int):
        if not (0 <= network_id <= 16):
            raise errors.ATCommandError(message="Network ID must be between 0 and 16")

        await self.__send(f"AT+NETWORKID={network_id}")

    async def get_network_id(self):
        response = await self.__send("AT+NETWORKID?")
        # Response format: +NETWORKID=<value>
        value = int(response.split("=")[1])
        return value

    async def set_mode(self, mode: RLYR896_MODE):
        await self.__send(f"AT+MODE={mode.value}")

    async def set_ipr(self, rate: int):
        if rate not in [300, 1200, 4800, 9600, 28800, 38400, 57600, 115200]:
            raise errors.ATCommandError(message=f"{rate} is not a valid Baud rate")
        await self.__send(f"AT+IPR={rate}")

    async def get_ipr(self):
        response = await self.__send("AT+IPR?")
        # Response format: +IPR=<value>
        value = int(response.split("=")[1])
        return value

    async def set_parameters(
        self, spreading_factor: int, bandwidth: int, coding_rate: int, preamble: int
    ):
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

    async def get_parameters(self):
        response = await self.__send("AT+PARAMETER?")
        # Response format: +PARAMETER=<sf>,<bw>,<cr>,<pp>
        values = response.split("=")[1].split(",")
        return {
            "spreading_factor": int(values[0]),
            "bandwidth": int(values[1]),
            "coding_rate": int(values[2]),
            "preamble": int(values[3])
        }

    async def set_freq(self, freq: RLYR896_FREQ):
        await self.__send(f"AT+BAND={freq.value}")

    async def get_freq(self):
        response = await self.__send("AT+BAND?")
        # Response format: +BAND=<value>
        value = int(response.split("=")[1])
        try:
            return RLYR896_FREQ(value)
        except ValueError:
            return value

    async def set_pass(self, password: str):
        if not CPIN_REGEX.fullmatch(password):
            raise errors.ATCommandError(message="Password must be 32 characters of Hex")

        await self.__send(f"AT+CPIN={password}")

    async def set_power(self, power: int):
        if not (0 <= power < 20):
            raise errors.ATCommandError(message="Power must be between 0 and 20")

        await self.__send(f"AT+CRFOP={power}")

    async def get_power(self):
        response = await self.__send("AT+CRFOP?")
        # Response format: +CRFOP=<value>
        value = int(response.split("=")[1])
        return value

    # TODO: Maybe rewrite send/rec to not depend on a queue?
    # Figure out if AT will send multiple errors/
    async def __send(self, data: str, ignore_ready: bool = False):
        log.debug(f"trying to send {data}")

        if self.rec_task is None or self.rec_task.done():
            raise errors.RecLoopNotRunning

        if not self.ready and not ignore_ready:
            raise errors.NotReady

        async with self.send_lock:
            log.debug(f"Lock acquired, ready, sending {data}")

            # Empty command response, no clutter.
            while not self.command_response.empty():
                await self.command_response.get()

            self.writer.write(data.encode())
            self.writer.write(b"\r\n")
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
            data = ""
            try:
                data = await self.reader.readline()
            except Exception as e:
                log.error(f"read line error: {e}")
            if not data:
                continue
            data = data.decode().strip()
            if data.startswith("+ERR"):
                log.error(f"Error: {data}")
                await self.command_response.put(data)
            elif data.startswith("+READY"):
                self.ready = True
            elif data.startswith("+RCV"):
                await self.message_queue.put(data)
            else:
                await self.command_response.put(data)
