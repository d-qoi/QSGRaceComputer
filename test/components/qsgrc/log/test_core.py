import asyncio
import logging
import pytest

import valkey.asyncio as valkey

from qsgrc.log import core
from qsgrc.log import valkey_sink


@pytest.mark.asyncio
async def test_valkey_log():
    TEST_STREAM = "test_valkey_log_stream"

    valkey_client = valkey.from_url("valkey://localhost:6379")
    await valkey_client.xtrim(TEST_STREAM, 0) #Reset Stream to 0

    handler = valkey_sink.ValkeyStreamHandler(TEST_STREAM, valkey_client=valkey_client)
    logger = core.get_logger(__name__, handler)
    logger.setLevel(logging.DEBUG)
    handler.setLevel(logging.DEBUG)

    logger.debug("Debug")
    logger.info("Info")
    logger.warning("Warn")
    logger.error("Error")
    logger.critical("Critical")

    await asyncio.sleep(0.1)

    count = await valkey_client.xlen(TEST_STREAM)

    assert count == 5

    res = await valkey_client.xread(streams={TEST_STREAM:0}, count=5)

    print(res)
