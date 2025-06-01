"""Configuration model."""

from utils.model import CloudflareConfig, ConfigBaseModel


class CloudflareTunnelIngressConfig(ConfigBaseModel):
    service: str
    hostname: str
    origin_server_name: str | None = None


class CloudflareDConfig(ConfigBaseModel):
    version: str
    ingress: list[CloudflareTunnelIngressConfig] = []


class ComponentConfig(ConfigBaseModel):
    cloudflare: CloudflareConfig
    cloudflared: CloudflareDConfig
