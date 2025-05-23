from enum import Enum
from pathlib import Path
from psutil import boot_time
from pydantic import NatsDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    def validate_log_level(cls, value: str):
        return LogLevel(value)

    nats_url: NatsDsn = NatsDsn("nats://localhost:4222")

    lora_url: str = "/dev/ttyUSB0"
    lora_address: int = 5
    lora_network_id: int = 2
    lora_target_address: int = 0
    obd2_url: str | None = None

    config_file: Path = Path(Path.home() / ".config" / "config.json")

    www_path: Path = Path("/var/www")




config = Config()
