"""Observability stack deployment."""

import pulumi as p
import pulumi_kubernetes as k8s

from observability.alloy import create_alloy
from observability.gateway import create_loki_gateway_service, create_mimir_gateway_service
from observability.grafana import create_grafana
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

    loki = create_loki(component_config, k8s_opts=k8s_opts)
    mimir = create_mimir(component_config, k8s_opts=k8s_opts)
    loki_gateway = create_loki_gateway_service(loki, k8s_opts)
    mimir_gateway = create_mimir_gateway_service(mimir, k8s_opts)
    create_grafana(
        component_config,
        loki_gateway=loki_gateway,
        mimir_gateway=mimir_gateway,
        k8s_opts=k8s_opts,
    )
    create_alloy(
        component_config,
        loki_gateway=loki_gateway,
        mimir_gateway=mimir_gateway,
        k8s_opts=k8s_opts,
    )

    p.export('phase', 'phase-5-alloy-gateway')
    p.export('namespace', ns.metadata['name'])
