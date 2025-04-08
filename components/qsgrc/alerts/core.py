from asyncio import Queue, Task, wait_for
from typing import Any

from qsgrc.log import get_logger
from qsgrc.messages import AlertMessage, AlertConditions


logger = get_logger("alerts")


MonitorConditions = tuple[AlertConditions, bool, float]


class MonitorAlerts:
    def __init__(
        self, name: str, out_stream: Queue, in_stream: Queue | None = None
    ) -> None:
        self.name: str = name
        self.out_stream = out_stream
        self.in_stream = in_stream
        self.rules: dict[str, MonitorConditions] = {}
        self.alert_conditions: dict[str, bool] = {}
        self.__task = Task | None

    def add_rule(
        self,
        listen_to: str,
        condition: AlertConditions,
        threshold: float,
        hold: bool = True,
    ) -> None:
        self.rules[listen_to] = (condition, hold, threshold)

    def remove_rule(self, listen_to: str) -> None:
        del self.rules[listen_to]

    def reset_alert_conditions(self) -> None:
        self.alert_conditions.clear()

    async def __loop(self):
        pass

    async def start(self):
        if self.in_stream:
            pass

    async def stop(self):
        pass
        

    async def __send_alert_update(self, listen_to: str, value: Any) -> None:
        await self.out_stream.put(
            AlertMessage(
                self.name,
                listen_to,
                self.alert_conditions.get(listen_to, False),
                str(value),
            )
        )

    async def check(self, listen_to: str, value: float) -> None:
        if listen_to not in self.rules:
            return

        condition, hold, threshold = self.rules[listen_to]
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
        if self.alert_conditions.get(listen_to, False):
            if alert:
                return
            elif hold:
                return
            else:
                self.alert_conditions[listen_to] = False
                await self.__send_alert_update(listen_to, value)
        elif alert:
            self.alert_conditions[listen_to] = True
            await self.__send_alert_update(listen_to, value)
