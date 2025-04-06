import asyncio
import nats
import json
import time
import signal
import sys
from datetime import datetime

async def main():
    # Connect to NATS
    nc = await nats.connect("nats://localhost:4222")
    
    # Handle graceful shutdown
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        print("\nShutting down publisher...")
        asyncio.create_task(nc.close())
        loop.stop()
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    print("Publishing time every second. Press Ctrl+C to exit.")
    
    try:
        # Publish time every second
        while True:
            current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            message = {
                "timestamp": time.time(),
                "formatted_time": current_time
            }
            
            await nc.publish("time.updates", json.dumps(message).encode())
            print(f"Published: {current_time}")
            await asyncio.sleep(1)
    finally:
        # Ensure connection is closed
        await nc.close()
        print("Publisher stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    sys.exit(0)

