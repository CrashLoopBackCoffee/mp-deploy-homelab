"""Configuration model."""

from utils.model import CloudflareConfig, ConfigBaseModel, get_pulumi_project


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


class StackConfig(ConfigBaseModel):
    model_config = {
        'alias_generator': lambda field_name: f'{get_pulumi_project(__file__)}:{field_name}'
    }
    config: ComponentConfig


class PulumiConfigRoot(ConfigBaseModel):
    config: StackConfig
