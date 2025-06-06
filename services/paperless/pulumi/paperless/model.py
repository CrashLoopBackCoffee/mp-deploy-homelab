"""Configuration model."""

import pydantic

from utils.model import ConfigBaseModel, EnvVarRef


class PaperlessConfig(ConfigBaseModel):
    version: str
    port: pydantic.PositiveInt = 8000
    data_size_gb: pydantic.PositiveInt
    media_size_gb: pydantic.PositiveInt
    consume_size_mb: pydantic.PositiveInt
    export_size_gb: pydantic.PositiveInt
    exporter_kubectl_version: str
    exporter_schedule: str = '30 3 * * *'
    external_hostname: str | None = None


class RedisConfig(ConfigBaseModel):
    version: str
    port: pydantic.PositiveInt = 6379


class EntraIdConfig(ConfigBaseModel):
    tenant_id: str = '19d0fb13-2d87-4699-9ae2-6e431148a6ae'
    client_id: str
    client_secret: str


class RCloneConfig(ConfigBaseModel):
    version: str
    rclone_conf_b64: EnvVarRef
    """Base64 encoded rclone config file, including remote and refresh token."""
    sync_period_sec: pydantic.PositiveInt = 600
    destinations: list[str]


class ComponentConfig(ConfigBaseModel):
    paperless: PaperlessConfig
    redis: RedisConfig
    entraid: EntraIdConfig
    rclone: RCloneConfig | None = None
