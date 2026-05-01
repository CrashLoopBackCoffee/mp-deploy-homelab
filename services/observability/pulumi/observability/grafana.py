"""Grafana dashboard deployment."""

import pulumi as p
import pulumi_kubernetes as k8s
import pulumi_random as random

from observability.constants import GRAFANA_CHART_URL
from observability.model import ComponentConfig


def create_grafana(
    component_config: ComponentConfig,
    *,
    loki: k8s.helm.v3.Release,
    mimir: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> k8s.helm.v3.Release:
    admin_username = 'admin'
    admin_password = random.RandomPassword(
        'grafana-admin-password',
        length=64,
        special=False,
    ).result

    create_loki_gateway_service(loki, k8s_opts)
    create_mimir_gateway_service(mimir, k8s_opts)

    grafana = k8s.helm.v3.Release(
        'grafana',
        chart='grafana',
        version=component_config.grafana.version,
        repository_opts={'repo': GRAFANA_CHART_URL},
        values={
            'adminUser': admin_username,
            'adminPassword': admin_password,
            'persistence': {'enabled': False},
            'testFramework': {'enabled': False},
            'datasources': {
                'datasources.yaml': {
                    'apiVersion': 1,
                    'datasources': [
                        {
                            'name': 'Mimir',
                            'type': 'prometheus',
                            'access': 'proxy',
                            'url': 'http://mimir.observability.svc.cluster.local/prometheus',
                            'isDefault': True,
                            'jsonData': {
                                'httpMethod': 'POST',
                            },
                        },
                        {
                            'name': 'Loki',
                            'type': 'loki',
                            'access': 'proxy',
                            'url': 'http://loki-gateway.observability.svc.cluster.local',
                            'isDefault': False,
                        },
                    ],
                },
            },
        },
        opts=k8s_opts,
    )

    service = grafana.status.apply(
        lambda status: k8s.core.v1.Service.get(
            'grafana-service',
            f'{status.namespace}/{status.name}',
            opts=k8s_opts,
        )
    )

    k8s.apiextensions.CustomResource(
        'grafana-ingress',
        api_version='traefik.io/v1alpha1',
        kind='IngressRoute',
        metadata={'name': 'grafana-ingress'},
        spec={
            'entryPoints': ['websecure'],
            'routes': [
                {
                    'kind': 'Rule',
                    'match': p.Output.concat('Host(`', component_config.ingress.hostname, '`)'),
                    'services': [
                        {
                            'name': service.metadata.name,
                            'namespace': service.metadata.namespace,
                            'port': 'service',
                        },
                    ],
                },
            ],
            # use default wildcard certificate:
            'tls': {},
        },
        opts=k8s_opts,
    )

    p.export('grafana-hostname', component_config.ingress.hostname)
    p.export('grafana-admin-username', admin_username)
    p.export('grafana-admin-password', admin_password)

    return grafana


def create_loki_gateway_service(
    loki: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> None:
    k8s.core.v1.Service(
        'loki-gateway',
        metadata={'name': 'loki-gateway'},
        spec={
            'selector': {
                'app.kubernetes.io/component': 'gateway',
                'app.kubernetes.io/instance': loki.status.name,
                'app.kubernetes.io/name': 'loki',
            },
            'ports': [
                {
                    'name': 'http',
                    'port': 80,
                    'target_port': 'http-metrics',
                }
            ],
        },
        opts=k8s_opts,
    )


def create_mimir_gateway_service(
    mimir: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> None:
    k8s.core.v1.Service(
        'mimir',
        metadata={'name': 'mimir'},
        spec={
            'selector': {
                'app.kubernetes.io/component': 'nginx',
                'app.kubernetes.io/instance': mimir.status.name,
                'app.kubernetes.io/name': 'mimir',
            },
            'ports': [
                {
                    'name': 'http',
                    'port': 80,
                    'target_port': 'http-metric',
                }
            ],
        },
        opts=k8s_opts,
    )
