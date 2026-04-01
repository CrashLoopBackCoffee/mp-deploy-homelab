"""Phase 1 scaffold helpers for the observability stack."""

import pulumi as p

from observability.model import ComponentConfig

NAMESPACE = 'observability'


def export_scaffold_outputs(component_config: ComponentConfig) -> None:
    """Export stable metadata for the initial scaffold-only phase."""
    del component_config

    p.export('phase', 'phase-1-scaffold')
    p.export('namespace', NAMESPACE)
