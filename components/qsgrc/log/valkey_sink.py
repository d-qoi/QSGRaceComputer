import asyncio
from logging import Handler, LogRecord
from time import time

from valkey.asyncio import Valkey

from qsgrc.config import config, boot_time


class ValkeyStreamHandler(Handler):
    def __init__(self, stream_name: str, valkey_client: Valkey | None = None):
        super().__init__()
        self.stream_name = stream_name

        self.client = valkey_client or Valkey.from_url(str(config.valkey_url))

    async def _emit(self, record: LogRecord):
        uptime = time() - boot_time
        entry = self.format(record)
        await self.client.xadd(
            self.stream_name, {"ts": uptime, record.name: entry}, maxlen=2000
        )

    def emit(self, record: LogRecord):
        asyncio.ensure_future(self._emit(record))
