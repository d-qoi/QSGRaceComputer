import asyncio
import sys
import valkey.asyncio as valkey
import argparse

from qsgrc.log import get_logger
from qsgrc.config import config

STOP_WORD = "STOPSTOPSTOP"

async def get_valkey():
    return valkey.from_url(str(config.valkey_url))

async def consumer():
    print("Starting Consumer")

async def producer():
    print("Starting Producer")

async def main():
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--consumer", action="store_true")
    group.add_argument("--producer", action="store_true")
    args = parser.parse_args()
    print(args)
    coro = None
    if args.consumer:
        coro = consumer()
    elif args.producer:
        coro = producer()
    else:
        print("Please pass --consumer or --producer")
        sys.exit(1)
    asyncio.run(coro)
