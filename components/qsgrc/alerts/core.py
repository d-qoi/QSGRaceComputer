from asyncio import Queue
from typing import Any, Dict, Optional, Tuple

from qsgrc.log import get_logger
from qsgrc.messages import AlertMessage, AlertConditions


logger = get_logger("alerts")


MonitorConditions = Tuple[AlertConditions, bool, Any, str]


class MonitorAlerts:
    def __init__(self, name: str, out_stream: Queue, in_stream: Optional[Queue] = None) -> None:
        self.name = name
        self.out_stream = out_stream
        self.in_stream = in_stream
        self.rules: Dict[str, MonitorConditions] = {}
        self.alert_conditions: Dict[str, bool] = {}

    def add_rule(
        self,
        listen_to: str,
        condition: AlertConditions,
        threshold: Any,
        msg: str = "",
        hold: bool = True,
    ) -> None:
        if msg == "":
            msg = f"Alert! {listen_to}"
        self.rules[listen_to] = (condition, hold, threshold, msg)

    def remove_rule(self, listen_to: str) -> None:
        self.rules.pop(listen_to)

    def reset_alert_conditions(self) -> None:
        self.alert_conditions.clear()

    async def __send_alert_update(self, listen_to: str, msg: str, value: Any) -> None:
        await self.out_stream.put(AlertMessage(self.name, listen_to, str(value)))

    async def check(self, listen_to: str, value: Any) -> None:
        if listen_to not in self.rules:
            return

        condition, hold, threshold, msg = self.rules[listen_to]
        alert = False
        if condition is AlertConditions.GT:
            alert = value > threshold
        if condition is AlertConditions.GTE:
            alert = value >= threshold
        if condition is AlertConditions.LT:
            alert = value < threshold
        if condition is AlertConditions.LTE:
            alert = value <= threshold
        if condition is AlertConditions.EQ:
            alert = value == threshold
        # Alert condition is already set
        if self.alert_conditions[listen_to]:
            if alert:
                return
            elif hold:
                return
            else:
                self.alert_conditions[listen_to] = False
                await self.__send_alert_update(listen_to, msg, value)
        elif alert:
            self.alert_conditions[listen_to] = True
            await self.__send_alert_update(listen_to, msg, value)
