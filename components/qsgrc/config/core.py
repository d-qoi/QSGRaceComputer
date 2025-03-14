from enum import Enum
from psutil import boot_time
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from qsgrc.config.valkeydns import ValkeyDns

boot_time = boot_time()

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class Config(BaseSettings):
    model_config = SettingsConfigDict(validate_default=False)

    log_level: LogLevel = LogLevel.WARNING

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, value):
        if isinstance(value, str):
            value = value.upper()
        return LogLevel(value)

    valkey_url: ValkeyDns = ValkeyDns("valkey://localhost:6379")
    valkey_log_sink: str = "log_sink"
    valkey_data_sink: str = "datalog"


config = Config()
