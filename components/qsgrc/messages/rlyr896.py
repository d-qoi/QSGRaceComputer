from typing import final, override
from qsgrc.messages.core import BaseMessage


@final
class LoRaConfigParams(BaseMessage):
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
        base = super().unpack(data)
        if base.name != cls.name:
            raise ValueError(f"name mismatch: {cls.name} != {base.name}")

        parts = base.value.split(".")
        if len(parts) != 4:
            raise ValueError("Invalid parameter format")

        return cls(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))


@final
class LoRaConfigPassword(BaseMessage):
    leader = "CL2"
    name = "PASS"

    def __init__(self, value: str):
        super().__init__(self.name, value)


@final
class LoRaConfigNetwork(BaseMessage):
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
        base = super().unpack(data)
        if base.name != cls.name:
            raise ValueError(f"name mismatch: {cls.name} != {base.name}")

        parts = base.value.split(".")
        if len(parts) != 2:
            raise ValueError("Invalid parameter format")

        return cls(int(parts[0]), int(parts[1]))
