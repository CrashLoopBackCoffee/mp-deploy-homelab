"""Phase 3 namespace and core services for the observability stack."""

import pulumi as p
import pulumi_kubernetes as k8s

from observability.loki import create_loki
from observability.mimir import create_mimir
from observability.model import ComponentConfig


def create_observability(
    component_config: ComponentConfig,
    k8s_provider: k8s.Provider,
) -> None:
    ns = k8s.core.v1.Namespace(
        'observability',
        metadata={'name': 'observability'},
        opts=p.ResourceOptions(provider=k8s_provider),
    )

    namespaced_k8s_provider = k8s.Provider(
        'observability-provider',
        kubeconfig=k8s_provider.kubeconfig,  # pyright: ignore[reportAttributeAccessIssue]
        namespace=ns.metadata['name'],
    )
    k8s_opts = p.ResourceOptions(provider=namespaced_k8s_provider)

    create_loki(component_config, k8s_opts=k8s_opts)
    create_mimir(component_config, k8s_opts=k8s_opts)

    p.export('phase', 'phase-3-namespace-and-core-services')
    p.export('namespace', ns.metadata['name'])
