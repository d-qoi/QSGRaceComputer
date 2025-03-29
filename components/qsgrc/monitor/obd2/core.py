from asyncio import (
    Condition,
    Event,
    Queue,
    Task,
    gather,
    get_event_loop,
    timeout,
    create_task,
    sleep,
)
from time import perf_counter
from typing import Any, Coroutine, Optional, Callable, Tuple

from obd import OBD, OBDCommand, OBDResponse

from qsgrc.log import get_logger

logger = get_logger("mon.obd2")


CommandCallback = Optional[Callable[[OBDResponse], None]]
CommandTuple = Tuple[str, CommandCallback]
ResponseTuple = Tuple[str, OBDResponse]

class OBD2Monitor(OBD):
    def __init__(
        self,
        portstr=None,
        baudrate=None,
        protocol=None,
        fast=True,
        timeout=0.1,
        check_voltage=True,
        start_low_power=False,
        delay_cmds=0.25,
    ):
        self.__tasks: list[Task] = []
        self.__running: bool = False
        self.__delay_cmds: float = delay_cmds
        self.__command_response: Queue[ResponseTuple] = Queue()
        # command queues
        self.high_priority: list[CommandTuple] = []
        self.low_priority: list[CommandTuple] = []
        self.oneshot_queue: Queue[CommandTuple] = Queue()

        # self.conn = OBD(
        #     portstr=portstr,
        #     baudrate=baudrate,
        #     protocol=protocol,
        #     fast=fast,
        #     timeout=timeout,
        #     check_voltage=check_voltage,
        #     start_low_power=start_low_power,
        # )
        logger.info(f"Initializing OBD2Monitor with port={portstr}, baudrate={baudrate}, protocol={protocol}")
        super().__init__(
            portstr=portstr,
            baudrate=baudrate,
            protocol=protocol,
            fast=fast,
            timeout=timeout,
            check_voltage=check_voltage,
            start_low_power=start_low_power,
        )

    async def start(self):
        self.__running = True
        if self.__tasks:
            return
        self.__tasks.append(create_task(self.__run_loop()))

    async def stop(self):
        self.__running = False
        try:
            async with timeout(5):
                await gather(*self.__tasks)
        except TimeoutError:
            logger.warning("Force Stopping Execution of tasks")
            for task in self.__tasks:
                task.cancel()

    def close(self):
        if self.__running:
            self.__running = False
            for task in self.__tasks:
                task.cancel()
        super().close()

    def add_high_priority(self, command, callback=None):
        if not any(cmd == command for cmd, _ in self.high_priority):
            self.high_priority.append((command, callback))
            return True
        return False

    def add_low_priority(self, command, callback=None):
        if not any(cmd == command for cmd, _ in self.low_priority):
            self.low_priority.append((command, callback))
            return True
        return False

    def clear_high_priority(self):
        self.high_priority.clear()

    def clear_low_priority(self):
        self.low_priority.clear()

    def remove_high_priority(self, command: str) -> bool:
        length = len(self.high_priority)
        self.high_priority = [(cmd, callback) for (cmd, callback) in self.high_priority if cmd != command]
        return length != len(self.high_priority)

    def remove_low_priority(self, command: str) -> bool:
        length = len(self.low_priority)
        self.low_priority = [(cmd, callback) for (cmd, callback) in self.low_priority if cmd != command]
        return length != len(self.low_priority)

    async def oneshot(self, command: str):
        """Queue a command to be executed once in the next cycle"""
        result = None
        oneshot_event = Event()

        def callback(response: OBDResponse) -> None:
            nonlocal result
            result = response
            oneshot_event.set()

        await self.oneshot_queue.put((command, callback))
        await oneshot_event.wait()
        return result

    async def __run_loop(self):
        high_priority = Queue()
        low_priority = Queue()
        while self.__running:
            # Get Next Command
            next_command = None
            # One Shots get highest priority, and only run once.
            if not self.oneshot_queue.empty():
                next_command = await self.oneshot_queue.get()
            # High Priority Commands will empty their queue first
            elif not high_priority.empty():
                next_command = await high_priority.get()
            # Low Priority Command, one will run every time the high priority queue empties
            elif not low_priority.empty():
                next_command = await low_priority.get()

            # Refill High Priority Command
            # Commands added/removed before the queue is done do not matter.
            if high_priority.empty():
                for command in self.high_priority:
                    high_priority.put_nowait(command)
            # Refill the low priority commands
            # Commands added/removed before the queue is done do not matter.
            if low_priority.empty():
                for command in self.low_priority:
                    low_priority.put_nowait(command)

            if next_command:
                (cmd, callback) = next_command
                try:
                    resp = self.query(cmd)
                    # If there is a callback, call it
                    if callback:
                        callback(resp)
                    # Always put response in the response queue.
                    await self.__command_response.put((cmd, resp))
                except Exception as e:
                    logger.error(f"Exception while processing {cmd}: {e}")
                    if callback:
                        callback(OBDResponse(cmd, "ERROR"))
            await sleep(self.__delay_cmds)
