from typing import Dict, Type
from re import compile
from qsgrc.messages.alerts import AlertConditions, AlertMessage, AlertConfigMessage, AlertConditionSet
from qsgrc.messages.rlyr896 import LoRaConfigNetwork, LoRaConfigParams, LoRaConfigPassword
from qsgrc.messages.core import BaseMessage, OBD2Datapoint, RequestConfig
from qsgrc.messages.core import SSEMessage

LEADER_REGEX = compile(r"^([A-Z0-9]+):")

MESSAGE_REGISTERY: Dict[str, Type[BaseMessage]] = {
    AlertConditionSet.leader: AlertConditionSet,
    AlertConfigMessage.leader: AlertConfigMessage,
    AlertMessage.leader: AlertMessage,
    LoRaConfigNetwork.leader: LoRaConfigNetwork,
    LoRaConfigParams.leader: LoRaConfigParams,
    LoRaConfigPassword.leader: LoRaConfigPassword,
    OBD2Datapoint.leader: OBD2Datapoint,
    RequestConfig.leader: RequestConfig,
    SSEMessage.leader: SSEMessage,
}

def unpack(message: str) -> BaseMessage:
    match = LEADER_REGEX.match(message)
    if not match:
        raise ValueError(f"Invalid Message Format: {message}")
    leader = match.group(1)
    if leader not in MESSAGE_REGISTERY:
        raise ValueError(f"Unknown Leader: {message}")

    return MESSAGE_REGISTERY[leader].unpack(message)

__all__ = [
    "AlertConditionSet",
    "AlertConditions",
    "AlertConfigMessage",
    "AlertMessage",
    "BaseMessage",
    "LoRaConfigNetwork",
    "LoRaConfigParams",
    "LoRaConfigPassword",
    "OBD2Datapoint",
    "RequestConfig",
    "SSEMessage",
    "unpack",
]
