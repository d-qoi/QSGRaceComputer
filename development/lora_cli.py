#!/usr/bin/env python3

# From ClaudLLM

import asyncio
import sys
import argparse
from enum import Enum
import re
from typing import Optional
from hashlib import sha256


class LoRaConfigParams:
    def __init__(self, spreading_factor=10, bandwidth=7, coding_rate=1, preamble=5):
        self.spreading_factor = spreading_factor
        self.bandwidth = bandwidth
        self.coding_rate = coding_rate
        self.preamble = preamble


# Import your RLYR896 class and other necessary imports
# Replace this with actual imports when using
from qsgrc.RYLR896 import RLYR896, RLYR896_FREQ, RLYR896_MODE
from qsgrc.config import config


async def print_message_queue(queue):
    """Print messages from the queue as they arrive"""
    while True:
        message = await queue.get()
        print(f"\nReceived: {message}")
        print(">> ", end="", flush=True)


async def run_shell(port, params):
    message_queue = asyncio.Queue()
    lora = RLYR896(
        url=port,
        params=params,
        message_steam=message_queue,
        address=config.lora_address,
        network_id=config.lora_network_id,
    )

    print(f"Connecting to LoRa device at {port}...")
    await lora.connect()

    print("Starting device...")
    await lora.start()

    print("Device ready!")
    print("\nAvailable commands:")
    print("  send <address> <message> - Send message to specific address")
    print("  address [new_address]    - Get or set device address")
    print("  netid [new_id]           - Get or set network ID")
    print("  freq [low|high]          - Get or set frequency")
    print("  param                    - Get current parameters")
    print("  power [level]            - Get or set power level (0-19)")
    print("  ping                     - Check if device is responding")
    print("  reset                    - Soft reset the device")
    print("  quit                     - Exit the program")

    # Start message queue listener
    asyncio.create_task(print_message_queue(message_queue))

    while True:
        try:
            cmd = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("\n>> ")
            )

            parts = cmd.strip().split()
            if not parts:
                continue

            command = parts[0].lower()

            if command == "quit" or command == "exit":
                break

            elif command == "send" and len(parts) >= 3:
                address = int(parts[1])
                message = " ".join(parts[2:])
                await lora.send(address, message)
                print(f"Message sent to address {address}")

            elif command == "address":
                if len(parts) > 1:
                    address = int(parts[1])
                    await lora.set_address(address)
                    print(f"Address set to {address}")
                else:
                    address = await lora.get_address()
                    print(f"Current address: {address}")

            elif command == "netid":
                if len(parts) > 1:
                    netid = int(parts[1])
                    await lora.set_network_id(netid)
                    print(f"Network ID set to {netid}")
                else:
                    netid = await lora.get_network_id()
                    print(f"Current network ID: {netid}")

            elif command == "freq":
                if len(parts) > 1:
                    if parts[1].lower() == "low":
                        await lora.set_freq(RLYR896_FREQ.LOW)
                        print("Frequency set to LOW")
                    else:
                        await lora.set_freq(RLYR896_FREQ.HIGH)
                        print("Frequency set to HIGH")
                else:
                    freq = await lora.get_freq()
                    print(f"Current frequency: {freq}")

            elif command == "param":
                params = await lora.get_parameters()
                print(f"Parameters: {params}")

            elif command == "power":
                if len(parts) > 1:
                    power = int(parts[1])
                    await lora.set_power(power)
                    print(f"Power set to {power}")
                else:
                    power = await lora.get_power()
                    print(f"Current power: {power}")

            elif command == "pass":
                if len(parts) > 1:
                    password = parts[1]
                    await lora.set_pass(password)
                    print(f"Pass set to {password}")
                else:
                    password = await lora.get_pass()
                    print(f"Current password: {password}")

            elif command == "ping":
                result = await lora.ping()
                print(f"Ping result: {'Success' if result else 'Failed'}")

            elif command == "reset":
                await lora.soft_reset()
                print("Device reset. Waiting to reconnect...")
                # Wait for device to come back up
                await asyncio.sleep(2)
                await lora.start()
                print("Device ready!")

            else:
                print("Unknown command. Type 'help' for available commands.")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

    print("Shutting down...")
    await lora.stop()


def main():
    parser = argparse.ArgumentParser(description="LoRa device shell interface")
    parser.add_argument(
        "port", help="Serial port for the LoRa device (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument("--sf", type=int, default=10, help="Spreading factor (5-15)")
    parser.add_argument("--bw", type=int, default=7, help="Bandwidth (0-9)")
    parser.add_argument("--cr", type=int, default=1, help="Coding rate (1-10)")
    parser.add_argument("--pp", type=int, default=5, help="Preamble (0-15)")

    args = parser.parse_args()

    params = LoRaConfigParams(
        spreading_factor=args.sf,
        bandwidth=args.bw,
        coding_rate=args.cr,
        preamble=args.pp,
    )

    try:
        asyncio.run(run_shell(args.port, params))
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
