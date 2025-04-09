from asyncio import Queue, Task, create_task, gather, wait_for

from qsgrc.log import get_logger
from qsgrc.messages import AlertMessage, AlertConditions


logger = get_logger("alerts")


MonitorConditions = tuple[AlertConditions, bool, float]


class MonitorAlerts:
    def __init__(
        self,
        name: str,
        out_stream: Queue[AlertMessage],
        in_stream: Queue[tuple[str, float]] | None = None,
    ) -> None:
        self.name: str = name
        self.out_stream: Queue[AlertMessage] = out_stream
        self.in_stream: Queue[tuple[str, float]] | None = in_stream
        self.rules: dict[str, MonitorConditions] = {}
        self.alert_conditions: dict[str, bool] = {}
        self.running: bool = False
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

    def clear_all_alert_conditions(self) -> None:
        self.alert_conditions.clear()

    async def clear_alert_condition(self, listen_to: str):
        if listen_to in self.alert_conditions:
            del self.alert_conditions[listen_to]
        await self.__send_alert_update(listen_to, 0)

    async def __loop(self):
        if self.in_stream is None:
            self.running = False
            return
        while self.running:
            try:
                listen_to, value = await wait_for(self.in_stream.get(), 1)
                await self.check(listen_to, value)
            except TimeoutError:
                pass

    async def start(self):
        if self.in_stream:
            self.running = True
            self.__task = create_task(self.__loop())

    async def stop(self):
        self.running = False
        if self.__task is None or self.__task.done():
            return
        try:
            await wait_for(gather(self.__task), 5)
        except TimeoutError:
            self.__task.cancel()
            self.__task = None

    async def __send_alert_update(self, listen_to: str, value: float) -> None:
        await self.out_stream.put(
            AlertMessage(
                self.name,
                listen_to,
                self.alert_conditions.get(listen_to, False),
                value,
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
