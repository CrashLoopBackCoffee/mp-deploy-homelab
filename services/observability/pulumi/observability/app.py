"""Phase 2 shared config exports for the observability stack."""

import pulumi as p

from observability.model import ComponentConfig

NAMESPACE = 'observability'


def export_shared_config_outputs(component_config: ComponentConfig) -> None:
    """Export validated config metadata while infrastructure resources are pending."""
    p.export('phase', 'phase-2-shared-config')
    p.export('namespace', NAMESPACE)
    p.export('grafana_version', component_config.grafana.version)
    p.export('loki_version', component_config.loki.version)
    p.export('mimir_version', component_config.mimir.version)
    p.export('alloy_version', component_config.alloy.version)
    p.export('grafana_hostname', component_config.ingress.hostname)
