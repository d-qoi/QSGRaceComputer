import asyncio
import nats
import json
import signal
import sys

from nats.aio.msg import Msg


async def main():
    # Connect to NATS
    nc = await nats.connect("nats://localhost:4222")

    # Handle graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler():
        print("\nShutting down subscriber...")
        asyncio.create_task(nc.close())
        loop.stop()

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Message handler
    async def message_handler(msg: Msg):
        try:
            print(msg.subject)
            data = json.loads(msg.data.decode())
            print(f"Received: {data['formatted_time']}")
        except Exception as e:
            print(f"Error processing message: {e}")

    # Subscribe to time updates
    sub = await nc.subscribe("time.*.*", cb=message_handler)
    print("Subscribed to time updates. Press Ctrl+C to exit.")

    try:
        # Keep the subscription alive
        while True:
            await asyncio.sleep(1)
    finally:
        # Clean up subscription and connection
        await sub.unsubscribe()
        await nc.close()
        print("Subscriber stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    sys.exit(0)
