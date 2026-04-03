"""Configuration model for the observability stack scaffold."""

from utils.model import ConfigBaseModel, get_pulumi_project


class ComponentConfig(ConfigBaseModel):
    """Placeholder config model for the Phase 1 scaffold."""


class StackConfig(ConfigBaseModel):
    model_config = {
        'alias_generator': lambda field_name: f'{get_pulumi_project(__file__)}:{field_name}'
    }
    config: ComponentConfig


class PulumiConfigRoot(ConfigBaseModel):
    config: StackConfig
