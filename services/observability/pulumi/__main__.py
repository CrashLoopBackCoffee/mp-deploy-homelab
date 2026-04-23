"""Observability stack entrypoint."""

import pulumi as p

from observability.app import export_shared_config_outputs
from observability.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().get_object('config') or {})

export_shared_config_outputs(component_config)
