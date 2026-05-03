"""Grafana dashboard deployment."""

import pulumi as p
import pulumi_kubernetes as k8s
import pulumi_random as random

from observability.constants import GRAFANA_CHART_URL
from observability.gateway import service_http_url
from observability.model import ComponentConfig


def create_grafana(
    component_config: ComponentConfig,
    *,
    loki_gateway: k8s.core.v1.Service,
    mimir_gateway: k8s.core.v1.Service,
    k8s_opts: p.ResourceOptions,
) -> k8s.helm.v3.Release:
    admin_username = 'admin'
    admin_password = random.RandomPassword(
        'grafana-admin-password',
        length=64,
        special=False,
    ).result

    data_pvc = k8s.core.v1.PersistentVolumeClaim(
        'grafana-data',
        metadata={'name': 'grafana-data'},
        spec={
            'access_modes': ['ReadWriteOnce'],
            'storage_class_name': component_config.grafana.storage_class_name,
            'resources': {'requests': {'storage': f'{component_config.grafana.storage_size_gb}Gi'}},
        },
        opts=p.ResourceOptions.merge(
            k8s_opts,
            p.ResourceOptions(protect=p.get_stack().startswith('prod')),
        ),
    )

    grafana = k8s.helm.v3.Release(
        'grafana',
        chart='grafana',
        version=component_config.grafana.version,
        repository_opts={'repo': GRAFANA_CHART_URL},
        values={
            'adminUser': admin_username,
            'adminPassword': admin_password,
            'persistence': {
                'enabled': True,
                'type': 'pvc',
                'existingClaim': data_pvc.metadata.name,
            },
            'testFramework': {'enabled': False},
            'datasources': {
                'datasources.yaml': {
                    'apiVersion': 1,
                    'datasources': [
                        {
                            'name': 'Mimir',
                            'type': 'prometheus',
                            'access': 'proxy',
                            'url': service_http_url(mimir_gateway, '/prometheus'),
                            'isDefault': True,
                            'jsonData': {
                                'httpMethod': 'POST',
                            },
                        },
                        {
                            'name': 'Loki',
                            'type': 'loki',
                            'access': 'proxy',
                            'url': service_http_url(loki_gateway),
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
