from typing import final, override
from qsgrc.messages.core import BaseMessage


class LoRaConfig(BaseMessage):
    subject: str = "config.lora"


@final
class LoRaConfigParams(LoRaConfig):
    leader = "CL1"
    name = "PARAMS"

    def __init__(
        self, spreading_factor: int, bandwidth: int, coding_rate: int, preamble: int
    ):
        self.spreading_factor = spreading_factor
        self.bandwidth = bandwidth
        self.coding_rate = coding_rate
        self.preamble = preamble

        value = f"{spreading_factor}.{bandwidth}.{coding_rate}.{preamble}"
        super().__init__(self.name, value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "LoRaConfigParams":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        value = match.group(3)
        name = match.group(2)
        if name != cls.name:
            raise ValueError(f"name mismatch: {cls.name} != {name}")

        parts = value.split(".")
        if len(parts) != 4:
            raise ValueError("Invalid parameter format")

        return cls(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))


@final
class LoRaConfigPassword(LoRaConfig):
    leader = "CL2"
    name = "PASS"

    def __init__(self, _, value: str):
        super().__init__(self.name, value)


@final
class LoRaConfigNetwork(LoRaConfig):
    leader = "CL3"
    name = "NET"
    network_id: int
    address: int

    def __init__(self, network_id: int, address: int):
        self.network_id = network_id
        self.address = address
        self.value = f"{self.network_id}.{self.address}"
        super().__init__(self.name, self.value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "LoRaConfigNetwork":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        value = match.group(3)
        name = match.group(2)
        if name != cls.name:
            raise ValueError(f"name mismatch: {cls.name} != {name}")

        parts = value.split(".")
        if len(parts) != 2:
            raise ValueError("Invalid parameter format")

        return cls(int(parts[0]), int(parts[1]))
