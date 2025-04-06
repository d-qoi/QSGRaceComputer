from asyncio import Queue, run

import nats
from nats.aio.msg import Msg

from qsgrc.config import config
from qsgrc.log.core import get_logger
from qsgrc.RYLR896 import RLYR896_MODE, RLYR896_FREQ, RLYR896, errors
from qsgrc.messages import LoRaConfigParams, LoRaConfigPassword

logger = get_logger("service.lora")

LORA_PARAMS = LoRaConfigParams(10, 9, 1, 4)
LORA_PASSWORD = LoRaConfigPassword("QSGRC_LORAPASS")


class LoRa_Service:
    def __init__(self) -> None:
        self.immediate_stream: Queue[str] = Queue()
        self.high_priority_queue: Queue[str] = Queue()
        self.low_priority_queue: Queue[str] = Queue()
        self.incomming_stream: Queue[str] = Queue()

    async def transmit_handler(self, msg: Msg):
        msg.subject

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

        self.transmit = await self.nc.subscribe("lora.*", cb=self.transmit_handler)


def main():
    service = LoRa_Service()
    run(service.run())
