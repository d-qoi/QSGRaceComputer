from enum import Enum
from typing import final, override
from qsgrc.messages.core import BaseMessage


class AlertConditions(Enum):
    GT = 1
    GTE = 2
    LT = 3
    LTE = 4
    EQ = 5
    REMOVE = 6


@final
class AlertMessage(BaseMessage):
    leader = "A"
    subject = "alert.trigger"
    listen_to: str = ""
    triggered: bool = False
    val: float = 0

    def __init__(self, name: str, listen_to: str, triggered: bool, val: float):

        self.val = val
        self.listen_to = listen_to
        self.triggered = triggered

        value = f"{listen_to}@{int(triggered)}@{val}"
        super().__init__(name, value)

    @override
    @classmethod
    def unpack(cls, data: str):
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError(f"Data did not match regex: {data}")
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")

        name = match.group(2)
        value = match.group(3)

        listen_to, triggered, val_str = value.split("@")

        # Try to convert to float, or keep as error string
        try:
            val = float(val_str)
        except ValueError as e:
            # If conversion fails, keep the original string
            raise e

        return cls(name, listen_to, bool(int(triggered)), val)


@final
class AlertConfigMessage(BaseMessage):
    leader = "AC"
    subject = "config.alert"
    listen_to: str = ""
    condition: AlertConditions
    threshold: float = 0.0
    hold: bool = False

    def __init__(
            self, name: str, listen_to: str, condition: AlertConditions, threshold: float, hold: bool
    ):
        self.listen_to = listen_to
        self.condition = condition
        self.threshold = threshold
        self.hold = hold

        value = f"{listen_to}@{condition.name}@{threshold}@{int(hold)}"
        super().__init__(name, value)

    @override
    @classmethod
    def unpack(cls, data: str) -> "AlertConfigMessage":
        match = cls.match_re.fullmatch(data)
        if not match:
            raise ValueError
        elif match.group(1) != cls.leader:
            raise ValueError(f"leader mismatch: {cls.leader} != {match.group(1)}")
        value = match.group(3)
        name = match.group(2)

        # Parse components using '#' as separator
        try:
            listen_to, condition_str, threshold_str, hold_str = value.split("@")

            # Convert string to enum
            condition = AlertConditions[condition_str]

            # Convert threshold to float
            threshold = float(threshold_str)

            hold = bool(int(hold_str))

            return cls(name, listen_to, condition, threshold, hold)

        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid format for AlertConfigMessage: {value}") from e


@final
class AlertConditionSet(BaseMessage):
    "Will force an alarm condition named 'name' to reset an alert condition for 'listen_to' as the value"
    leader = "ACS"

