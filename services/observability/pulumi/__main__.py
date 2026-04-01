"""Observability stack scaffold."""

import pulumi as p

from observability.app import export_scaffold_outputs
from observability.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().get_object('config') or {})

export_scaffold_outputs(component_config)
