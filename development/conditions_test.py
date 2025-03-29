from asyncio import Condition, TaskGroup
import asyncio
from random import randrange

async def multiple_waiters_example():
    condition = asyncio.Condition()
    data = []
    
    async def waiter(name):
        print(f"{name} waiting to acquire lock")
        async with condition:
            print(f"{name} acquired lock, waiting for condition")
            await condition.wait()
            print(f"{name} was notified and reacquired lock")
            # Now can safely access shared data
            await asyncio.sleep(randrange(1,4))
            print(f"{name} sees data: {data}")
            # Process for a bit while holding the lock
            await asyncio.sleep(randrange(1,4))
            print(f"{name} releasing lock")
    
    async def notifier():
        await asyncio.sleep(1)  # Let waiters queue up
        print("Notifier waiting to acquire lock")
        async with condition:
            print("Notifier acquired lock")
            data.append("new data")
            print("Notifier calling notify_all()")
            condition.notify_all()
            print("Notifier released lock")
    
    # Start multiple waiters
    waiters = [asyncio.create_task(waiter(f"Waiter-{i}")) for i in range(3)]
    notifier_task = asyncio.create_task(notifier())
    
    await asyncio.gather(notifier_task, *waiters)
