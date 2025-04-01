from enum import Enum
from typing import Union
from qsgrc.messages.core import BaseMessage


class AlertConditions(Enum):
    GT = 1
    GTE = 2
    LT = 3
    LTE = 4
    EQ = 5


class AlertMessage(BaseMessage):
    leader = "A"
    listen_to: str = ""
    triggered: bool = False
    val: Union[float, str] = ""

    def __init__(self, name: str, listen_to: str, triggered: bool = False, val: Union[float, str] = ""):
        val = val or ""

        self.val = val
        self.listen_to = listen_to
        self.triggered = triggered

        value = f"{listen_to}@{int(triggered)}@{val}"
        super().__init__(name, value)

    @classmethod
    def unpack(cls, data: str):
        match = cls.match_re.fullmatch(data)
        if not match:
            raise TypeError(f"Data did not match regex: {data}")
        elif match.group(1) != cls.leader:
            raise TypeError(f"leader mismatch: {cls.leader} != {match.group(1)}")

        name = match.group(2)
        value = match.group(3)

        listen_to, triggered, val_str = value.split("@")

        # Try to convert to float, or keep as error string
        try:
            val = float(val_str)
        except ValueError:
            # If conversion fails, keep the original string
            val = val_str

        return cls(name, listen_to, bool(triggered), val)


class AlertConfigMessage(BaseMessage):
    leader = "AC"
    listen_to: str = ""
    condition: AlertConditions
    threshold: float = 0.0
    msg: str = ""

    def __init__(
            self, name: str, listen_to: str, condition: AlertConditions, threshold: float,
            msg: str = ""
    ):
        self.listen_to = listen_to
        self.condition = condition
        self.threshold = threshold
        self.msg = ""

        value = f"{listen_to}@{condition.name}@{threshold}@{msg}"
        super().__init__(name, value)

    @classmethod
    def unpack(cls, data: str) -> "AlertConfigMessage":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise TypeError(f"Data did not match regex: {data}")
        elif match.group(1) != cls.leader:
            raise TypeError(f"leader mismatch: {cls.leader} != {match.group(1)}")

        name = match.group(2)
        value = match.group(3)

        # Parse components using '#' as separator
        try:
            listen_to, condition_str, threshold_str, msg = value.split("@")

            # Convert string to enum
            condition = AlertConditions[condition_str]

            # Convert threshold to float
            threshold = float(threshold_str)

            return cls(name, listen_to, condition, threshold, msg)

        except (ValueError, KeyError) as e:
            raise TypeError(f"Invalid format for AlertConfigMessage: {value}") from e


class AlertConditionSet(BaseMessage):
    leader = "ACS"
