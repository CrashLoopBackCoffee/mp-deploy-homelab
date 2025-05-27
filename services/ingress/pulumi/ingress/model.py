"""Configuration model."""

from utils.model import ConfigBaseModel, EnvVarRef


class CloudflareConfig(ConfigBaseModel):
    api_token: EnvVarRef


class ComponentConfig(ConfigBaseModel):
    cloudflare: CloudflareConfig
