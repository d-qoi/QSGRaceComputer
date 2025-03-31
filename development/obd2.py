import asyncio
from obd import OBDResponse

from qsgrc.monitor.obd2 import OBD2Monitor


async def test_obd2_monitor():
    # Initialize monitor with a mock port for testing
    # For actual hardware, use your port like "/dev/ttyUSB0"
    monitor = OBD2Monitor()

    # Add commands to priority queues
    monitor.add_high_priority("SPEED")
    monitor.add_high_priority("RPM")
    monitor.add_high_priority("ENGINE_LOAD")

    monitor.add_low_priority("COOLANT_TEMP")
    monitor.add_low_priority("INTAKE_TEMP")

    # Start the monitor
    await monitor.start()

    print(monitor.high_priority)
    print(monitor.low_priority)

    # Process responses for 15 seconds
    try:
        end_time = asyncio.get_event_loop().time() + 15
        while asyncio.get_event_loop().time() < end_time:
            cmd, response = await monitor.responses()
            print(f"{cmd}: {response.value}")
    finally:
        # Stop and close the monitor
        await monitor.stop()
        monitor.close()


if __name__ == "__main__":
    asyncio.run(test_obd2_monitor())
