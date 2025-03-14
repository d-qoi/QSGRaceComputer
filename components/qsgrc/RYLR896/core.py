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

from asyncio import Queue, Lock
from enum import Enum
import re

import serial_asyncio

from qsgrc.RYLR896 import errors

CPIN_REGEX = re.compile(r"([0-9a-f]){32}", re.IGNORECASE)


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
        self.rec_thread = None
        self.message_queue = Queue()
        self.command_response = Queue()
        self.send_lock = Lock()
        self.ready = False
        self.reader, self.writer = None, None

    async def connect(self):
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.url, baudrate=self.baudrate
        )

    async def ping(self):
        await self.__send("AT")

    async def soft_reset(self):
        await self.__send("AT+RESET", "+RESET")

    async def send(self, data: str, address: int=0):
        if 0 > address <= 65535:
            address = 0

        data_length = len(data)

        data.isascii

        if data_length > 240:
            raise errors.TXDataOverflowError()

        await self.__send(f"AT+SEND={address},{data_length},{data}")

    async def set_address(self, address: int):
        if 0 >= address > 65535:
            raise errors.ATCommandError(message="Address Out of Range")

        await self.__send(f"AT+SEND={address}")

    async def set_network(self, network_id: int):
        if 0 >= network_id > 16:
            raise errors.ATCommandError(message="Network ID must be between 0 and 16")

        await self.__send(f"AT+NETWORKID={network_id}")

    async def set_mode(self, mode: RLYR896_MODE):
        await self.__send(f"AT+MODE={mode.value}")

    async def set_ipr(self, rate: int):
        if rate not in [300, 1200, 4800, 9600, 28800, 38400, 57600, 115200]:
            raise errors.ATCommandError(message=f"{rate} is not a valid Baud rate")
        await self.__send(f"AT+IPR={rate}")

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

    async def set_freq(self, freq: RLYR896_FREQ):
        await self.__send(f"AT+BAND={freq.value}")

    async def set_pass(self, password: str):
        if not CPIN_REGEX.fullmatch(password):
            raise errors.ATCommandError(message="Password must be 32 characters of Hex")

        await self.__send(f"AT+CPIN={password}")

    async def set_power(self, power: int):
        if 0 >= power > 20:
            raise errors.ATCommandError(message="Power must be between 0 and 20")

        await self.__send(f"AT+CRFOP={power}")

    async def __send(self, data: str, resp: str = "+OK"):
        async with self.send_lock:
            print(data)

    async def __rec_loop(self, data: bytes):
        pass
