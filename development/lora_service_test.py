#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Any
import nats
from nats.aio.client import Client as NATS

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("lora-cli")


class LoRaCLI:
    def __init__(self):
        self.nc: Optional[NATS] = None
        self.tasks = []
        self.subscriptions = []
        self.running = True
        self.nats_server = "nats://localhost:4222"
        self.is_connected = False

    async def connect_nats(self, server: str = None) -> bool:
        """Connect to NATS server"""
        if server:
            self.nats_server = server

        try:
            logger.info(f"Connecting to NATS at {self.nats_server}")
            self.nc = await nats.connect(self.nats_server)
            logger.info("Connected to NATS")
            self.is_connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            self.is_connected = False
            return False

    async def send_message(self, subject: str, payload: str) -> None:
        """Send a message to NATS"""
        if not self.nc or not self.is_connected:
            logger.error("Not connected to NATS")
            print("❌ Not connected to NATS. Please connect first.")
            return

        try:
            logger.info(f"Sending message to {subject}: {payload}")
            await self.nc.publish(subject, payload.encode())
            print(f"✅ Message sent to {subject}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            print(f"❌ Failed to send message: {e}")

    async def message_handler(self, msg):
        """Handler for received messages"""
        subject = msg.subject
        data = msg.data.decode()
        print(f"\n📩 Received message on {subject}: {data}")
        print("> ", end="", flush=True)  # Restore prompt

    async def subscribe(self, subject: str) -> None:
        """Subscribe to a subject and handle messages"""
        if not self.nc or not self.is_connected:
            logger.error("Not connected to NATS")
            print("❌ Not connected to NATS. Please connect first.")
            return

        try:
            logger.info(f"Subscribing to {subject}")
            sub = await self.nc.subscribe(subject, cb=self.message_handler)
            self.subscriptions.append((subject, sub))
            print(f"✅ Subscribed to {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            print(f"❌ Failed to subscribe: {e}")

    async def unsubscribe(self, subject_idx: int) -> None:
        """Unsubscribe from a subject"""
        if not self.subscriptions:
            print("No active subscriptions")
            return

        if subject_idx < 0 or subject_idx >= len(self.subscriptions):
            print("❌ Invalid subscription index")
            return

        subject, sub = self.subscriptions[subject_idx]
        try:
            await sub.unsubscribe()
            print(f"✅ Unsubscribed from {subject}")
            self.subscriptions.pop(subject_idx)
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            print(f"❌ Failed to unsubscribe: {e}")

    async def list_subscriptions(self) -> None:
        """List all active subscriptions"""
        if not self.subscriptions:
            print("No active subscriptions")
            return

        print("\nActive subscriptions:")
        for i, (subject, _) in enumerate(self.subscriptions):
            print(f"{i}: {subject}")

    async def disconnect(self) -> None:
        """Disconnect from NATS"""
        if not self.nc or not self.is_connected:
            print("Not connected to NATS")
            return

        try:
            # Unsubscribe from all subscriptions
            for _, sub in self.subscriptions:
                await sub.unsubscribe()
            self.subscriptions = []

            # Close NATS connection
            await self.nc.close()
            self.is_connected = False
            print("✅ Disconnected from NATS")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            print(f"❌ Error disconnecting: {e}")

    async def send_lora_message(self, priority: str, ack: bool, message: str) -> None:
        """Send a message to LoRa service"""
        ack_str = "ack" if ack else "noack"
        subject = f"lora.{ack_str}.{priority}"
        await self.send_message(subject, message)

    async def configure_lora_params(
        self, spreading_factor: int, bandwidth: int, coding_rate: int, preamble: int
    ) -> None:
        """Configure LoRa parameters"""
        config_data = {
            "leader": "LORA_PARAMS",
            "spreading_factor": spreading_factor,
            "bandwidth": bandwidth,
            "coding_rate": coding_rate,
            "preamble": preamble,
        }
        await self.send_message("config.lora", json.dumps(config_data))

    async def configure_lora_network(self, network_id: int, address: int) -> None:
        """Configure LoRa network settings"""
        config_data = {
            "leader": "LORA_NETWORK",
            "network_id": network_id,
            "address": address,
        }
        await self.send_message("config.lora", json.dumps(config_data))

    async def configure_lora_password(self, password: str) -> None:
        """Configure LoRa password"""
        config_data = {"leader": "LORA_PASSWORD", "value": password}
        await self.send_message("config.lora", json.dumps(config_data))

    async def request_config(self) -> None:
        """Request LoRa configuration"""
        config_data = {"name": "LORA"}
        await self.send_message("request.config", json.dumps(config_data))

    def clear_screen(self) -> None:
        """Clear the terminal screen"""
        os.system("cls" if os.name == "nt" else "clear")

    async def main_menu(self) -> None:
        """Display and handle the main menu"""
        self.clear_screen()
        while self.running:
            print("\n=== LoRa Service CLI Test Tool ===")
            print(f"NATS Server: {self.nats_server}")
            print(
                f"Connection Status: {'Connected ✅' if self.is_connected else 'Disconnected ❌'}"
            )
            print("\nOptions:")
            print("1. Connect to NATS")
            print("2. Send LoRa Message")
            print("3. Subscribe to Topic")
            print("4. List/Manage Subscriptions")
            print("5. Configure LoRa Parameters")
            print("6. Configure LoRa Network")
            print("7. Configure LoRa Password")
            print("8. Request LoRa Configuration")
            print("9. Disconnect from NATS")
            print("0. Exit")

            choice = input("\nEnter your choice: ")

            if choice == "1":
                await self.connection_menu()
            elif choice == "2":
                await self.send_message_menu()
            elif choice == "3":
                await self.subscribe_menu()
            elif choice == "4":
                await self.subscription_management_menu()
            elif choice == "5":
                await self.config_params_menu()
            elif choice == "6":
                await self.config_network_menu()
            elif choice == "7":
                await self.config_password_menu()
            elif choice == "8":
                await self.request_config()
            elif choice == "9":
                await self.disconnect()
            elif choice == "0":
                self.running = False
                await self.disconnect()
                print("Exiting...")
                break
            else:
                print("Invalid choice, please try again.")

    async def connection_menu(self) -> None:
        """Handle NATS connection"""
        if self.is_connected:
            print("Already connected to NATS")
            input("Press Enter to continue...")
            return

        server = input(f"Enter NATS server URL [{self.nats_server}]: ")
        if not server:
            server = self.nats_server

        success = await self.connect_nats(server)
        if success:
            print(f"✅ Connected to {server}")
        else:
            print(f"❌ Failed to connect to {server}")

        input("Press Enter to continue...")

    async def send_message_menu(self) -> None:
        """Handle sending LoRa messages"""
        if not self.is_connected:
            print("❌ Not connected to NATS. Please connect first.")
            input("Press Enter to continue...")
            return

        print("\n=== Send LoRa Message ===")
        print("Priority levels:")
        print("1. Immediate")
        print("2. High")
        print("3. Low")

        priority_choice = input("Select priority [2]: ")
        if not priority_choice:
            priority_choice = "2"

        priority_map = {"1": "immediate", "2": "high", "3": "low"}
        if priority_choice not in priority_map:
            print("❌ Invalid priority, using high")
            priority = "high"
        else:
            priority = priority_map[priority_choice]

        ack_choice = input("Request acknowledgment? (y/n) [n]: ").lower()
        ack = ack_choice == "y"

        print("\nEnter message (Ctrl+D or empty line to finish):")
        message_lines = []
        while True:
            try:
                line = input()
                if not line and message_lines:  # Empty line finishes if we have content
                    break
                message_lines.append(line)
            except EOFError:
                break

        if message_lines:
            message = "\n".join(message_lines)
            await self.send_lora_message(priority, ack, message)
        else:
            print("❌ No message entered")

        input("Press Enter to continue...")

    async def subscribe_menu(self) -> None:
        """Handle subscribing to topics"""
        if not self.is_connected:
            print("❌ Not connected to NATS. Please connect first.")
            input("Press Enter to continue...")
            return

        print("\n=== Subscribe to Topic ===")
        print("Common topics:")
        print("1. All messages (#)")
        print("2. All LoRa messages (lora.>)")
        print("3. All LoRa acks (lora.ack.>)")
        print("4. LoRa configuration responses (config.lora.response)")
        print("5. Custom topic")

        choice = input("Select topic [1]: ")
        if not choice:
            choice = "1"

        topic_map = {
            "1": "#",
            "2": "lora.>",
            "3": "lora.ack.>",
            "4": "config.lora.response",
        }

        if choice == "5":
            topic = input("Enter custom topic: ")
        else:
            topic = topic_map.get(choice, "#")

        await self.subscribe(topic)
        input("Press Enter to continue...")

    async def subscription_management_menu(self) -> None:
        """Handle subscription management"""
        if not self.is_connected:
            print("❌ Not connected to NATS. Please connect first.")
            input("Press Enter to continue...")
            return

        await self.list_subscriptions()
        if not self.subscriptions:
            input("Press Enter to continue...")
            return

        print("\nOptions:")
        print("1. Unsubscribe")
        print("2. Return to main menu")

        choice = input("Enter your choice [2]: ")
        if choice == "1":
            idx = input("Enter subscription index to unsubscribe: ")
            try:
                await self.unsubscribe(int(idx))
            except ValueError:
                print("❌ Invalid index")

        input("Press Enter to continue...")

    async def config_params_menu(self) -> None:
        """Handle configuring LoRa parameters"""
        if not self.is_connected:
            print("❌ Not connected to NATS. Please connect first.")
            input("Press Enter to continue...")
            return

        print("\n=== Configure LoRa Parameters ===")
        try:
            sf = int(input("Enter spreading factor [10]: ") or "10")
            bw = int(input("Enter bandwidth [9]: ") or "9")
            cr = int(input("Enter coding rate [1]: ") or "1")
            preamble = int(input("Enter preamble [4]: ") or "4")

            await self.configure_lora_params(sf, bw, cr, preamble)
        except ValueError:
            print("❌ Invalid input, parameters must be integers")

        input("Press Enter to continue...")

    async def config_network_menu(self) -> None:
        """Handle configuring LoRa network"""
        if not self.is_connected:
            print("❌ Not connected to NATS. Please connect first.")
            input("Press Enter to continue...")
            return

        print("\n=== Configure LoRa Network ===")
        try:
            network_id = int(input("Enter network ID: "))
            address = int(input("Enter address: "))

            await self.configure_lora_network(network_id, address)
        except ValueError:
            print("❌ Invalid input, parameters must be integers")

        input("Press Enter to continue...")

    async def config_password_menu(self) -> None:
        """Handle configuring LoRa password"""
        if not self.is_connected:
            print("❌ Not connected to NATS. Please connect first.")
            input("Press Enter to continue...")
            return

        print("\n=== Configure LoRa Password ===")
        password = input("Enter password [QSGRC_LORAPASS]: ") or "QSGRC_LORAPASS"

        await self.configure_lora_password(password)
        input("Press Enter to continue...")


async def main():
    cli = LoRaCLI()
    try:
        await cli.main_menu()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await cli.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
