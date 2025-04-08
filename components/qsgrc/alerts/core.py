from asyncio import Queue
from typing import Any, Dict, Optional, Tuple

from qsgrc.log import get_logger
from qsgrc.messages import AlertMessage, AlertConditions


logger = get_logger("alerts")


MonitorConditions = tuple[AlertConditions, bool, float | str]


class MonitorAlerts:
    def __init__(
        self, name: str, out_stream: Queue[AlertMessage], in_stream: Queue[tuple[str, float|str]] | None = None
    ) -> None:
        self.name: str = name
        self.out_stream: Queue[AlertMessage] = out_stream
        self.in_stream: Queue[tuple[str, float|str]] | None = in_stream
        self.rules: dict[str, MonitorConditions] = {}
        self.alert_conditions: dict[str, bool] = {}

    def add_rule(
        self,
        listen_to: str,
        condition: AlertConditions,
        threshold: float | str,
        hold: bool = True,
    ) -> None:
        self.rules[listen_to] = (condition, hold, threshold)

    def remove_rule(self, listen_to: str) -> None:
        del self.rules[listen_to]

    def reset_alert_conditions(self) -> None:
        self.alert_conditions.clear()

    async def __send_alert_update(self, listen_to: str, value: float | str) -> None:
        await self.out_stream.put(
            AlertMessage(
                self.name,
                listen_to,
                self.alert_conditions.get(listen_to, False),
                str(value),
            )
        )

    async def check(self, listen_to: str, value: float | str) -> None:
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
