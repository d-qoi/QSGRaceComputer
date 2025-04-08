from asyncio import TaskGroup, get_running_loop, sleep


class async_gather_test:
    def __init__(self):
        self.tasks = []
        self.running = False

    async def long_running_task(self):
        print("Longer RUnning Task Start")
        await sleep(10)
        print("Longer running task done")

    async def short_running_task(self):
        print("short running task")
        await sleep(1)
        print("short running task complete")

    async def infinite_task(self, name = "infinite", wait_time=1):
        while self.running:
            print(f"{name} infinite task tick")
            await sleep(wait_time)

    def start(self):
        loop = get_running_loop()
        async with TaskGroup() as tg:
            pass
