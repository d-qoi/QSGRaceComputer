from asyncio import (
    Event,
    Queue,
    Task,
    gather,
    timeout,
    create_task,
    sleep,
)

import logging

from typing import Any, Optional, Callable, Tuple, List, cast

from obd import OBD, OBDStatus, OBDResponse
from obd import commands as OBDCommands

from qsgrc.log import get_logger

logger = get_logger("mon.obd2")
logger.setLevel(logging.DEBUG)

CommandCallback = Optional[Callable[[OBDResponse], None]]
CommandTuple = Tuple[str, CommandCallback]
ResponseTuple = Tuple[str, Any]


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
        self.__tasks: List[Task] = []
        self.__running: bool = False
        self.__delay_cmds: float = delay_cmds
        self.__command_response: Queue[ResponseTuple] = Queue()
        # command queues
        self.high_priority: List[CommandTuple] = []
        self.low_priority: List[CommandTuple] = []
        self.oneshot_queue: Queue[CommandTuple] = Queue()

        logger.info(
            f"Initializing OBD2Monitor with port={portstr}, baudrate={baudrate}, protocol={protocol}"
        )
        super().__init__(
            portstr=portstr,
            baudrate=baudrate,
            protocol=protocol,
            fast=fast,
            timeout=timeout,
            check_voltage=check_voltage,
            start_low_power=start_low_power,
        )

        if self.status() == OBDStatus.CAR_CONNECTED:
            logger.info("Successfully connected to vehicle")
        else:
            logger.warning(f"Connection status: {self.status()}")

    async def start(self) -> None:
        """Start the OBD monitoring tasks"""
        logger.info("Starting OBD2 monitor")
        self.__running = True
        if self.__tasks:
            logger.debug("Tasks already exist, ignoring start request")
            return
        self.__tasks.append(create_task(self.__run_loop()))
        logger.debug("Monitor task started")

    async def stop(self) -> None:
        """Stop all monitor tasks gracefully"""
        logger.info("Stopping OBD2 monitor")
        self.__running = False
        try:
            async with timeout(5):
                await gather(*self.__tasks)
                logger.debug("All tasks completed gracefully")
        except TimeoutError:
            logger.warning("Force Stopping Execution of tasks")
            for task in self.__tasks:
                task.cancel()

    def close(self) -> None:
        """Close the connection and cancel all tasks"""
        logger.info("Closing OBD2 monitor connection")
        if self.__running:
            logger.debug("Monitor still running, cancelling tasks")
            self.__running = False
            for task in self.__tasks:
                task.cancel()
        super().close()
        logger.debug("OBD2 connection closed")

    def add_high_priority(self, command: str, callback: CommandCallback = None) -> bool:
        """Add a command to the high priority list"""
        if not any(cmd == command for cmd, _ in self.high_priority):
            logger.debug(f"Adding high priority command: {command}")
            self.high_priority.append((command, callback))
            return True
        logger.debug(f"High priority command already exists: {command}")
        return False

    def add_low_priority(self, command: str, callback: CommandCallback = None) -> bool:
        """Add a command to the low priority list"""
        if not any(cmd == command for cmd, _ in self.low_priority):
            logger.debug(f"Adding low priority command: {command}")
            self.low_priority.append((command, callback))
            return True
        logger.debug(f"Low priority command already exists: {command}")
        return False

    def clear_high_priority(self) -> None:
        """Clear all high priority commands"""
        logger.info(f"Clearing {len(self.high_priority)} high priority commands")
        self.high_priority.clear()

    def clear_low_priority(self) -> None:
        """Clear all low priority commands"""
        logger.info(f"Clearing {len(self.low_priority)} low priority commands")
        self.low_priority.clear()

    def remove_high_priority(self, command: str) -> bool:
        """Remove a command from the high priority list"""
        length = len(self.high_priority)
        self.high_priority = [
            (cmd, callback) for (cmd, callback) in self.high_priority if cmd != command
        ]
        removed = length != len(self.high_priority)
        if removed:
            logger.debug(f"Removed high priority command: {command}")
        else:
            logger.debug(f"High priority command not found for removal: {command}")
        return removed

    def remove_low_priority(self, command: str) -> bool:
        """Remove a command from the low priority list"""
        length = len(self.low_priority)
        self.low_priority = [
            (cmd, callback) for (cmd, callback) in self.low_priority if cmd != command
        ]
        removed = length != len(self.low_priority)
        if removed:
            logger.debug(f"Removed low priority command: {command}")
        else:
            logger.debug(f"Low priority command not found for removal: {command}")
        return removed

    async def oneshot(self, command: str) -> OBDResponse:
        """Queue a command to be executed once in the next cycle"""
        logger.debug(f"Executing oneshot command: {command}")
        result: Optional[OBDResponse] = None
        oneshot_event = Event()

        def callback(response: OBDResponse) -> None:
            nonlocal result
            result = response
            oneshot_event.set()

        await self.oneshot_queue.put((command, callback))
        logger.debug(f"Waiting for oneshot response: {command}")
        await oneshot_event.wait()
        logger.debug(f"Received oneshot response for: {command}")
        return cast(OBDResponse, result)  # We know it's not None after the event

    async def responses(self) -> ResponseTuple:
        return await self.__command_response.get()

    def set_delay(self, delay: float):
        self.__delay_cmds = delay

    async def __run_loop(self) -> None:
        """Main command processing loop"""
        logger.info("Starting command processing loop")
        high_priority: Queue[CommandTuple] = Queue()
        low_priority: Queue[CommandTuple] = Queue()

        while self.__running:
            # Get Next Command
            next_command: Optional[CommandTuple] = None

            # One Shots get highest priority, and only run once.
            if not self.oneshot_queue.empty():
                logger.debug("Processing from oneshot queue")
                next_command = await self.oneshot_queue.get()
            # High Priority Commands will empty their queue first
            elif not high_priority.empty():
                logger.debug("Processing from high priority queue")
                next_command = await high_priority.get()

            # Refill High Priority Command
            # Commands added/removed before the queue is done do not matter.
            else:
                # Low Priority Command, one will run every time the high priority queue empties
                if not low_priority.empty() and next_command is None:
                    logger.debug("Processing from low priority queue")
                    next_command = await low_priority.get()

                logger.debug(
                    f"Refilling high priority queue with {len(self.high_priority)} commands"
                )
                for command in self.high_priority:
                    high_priority.put_nowait(command)

                # Refill the low priority commands
                # Commands added/removed before the queue is done do not matter.
                if low_priority.empty():
                    logger.debug(
                        f"Refilling low priority queue with {len(self.low_priority)} commands"
                    )
                    for command in self.low_priority:
                        low_priority.put_nowait(command)

            if next_command:
                (cmd, callback) = next_command
                try:
                    logger.debug(f"Executing command: {cmd}")
                    resp = self.query(OBDCommands[cmd])
                    # If there is a callback, call it
                    if callback:
                        logger.debug(f"Calling callback for command: {cmd}")
                        callback(resp)
                    # Always put response in the response queue.
                    await self.__command_response.put((cmd, resp))

                except Exception as e:
                    logger.error(f"Exception while processing {cmd}: {e}")
                    if callback:
                        logger.debug(f"Calling error callback for: {cmd}")
                        callback(OBDResponse(cmd, "ERROR"))
            else:
                logger.debug("No commands to process, waiting")
            await sleep(self.__delay_cmds)
