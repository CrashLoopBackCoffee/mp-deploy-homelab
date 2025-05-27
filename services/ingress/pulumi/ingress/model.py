"""Configuration model."""

from utils.model import CloudflareConfig, ConfigBaseModel


class ComponentConfig(ConfigBaseModel):
    cloudflare: CloudflareConfig
