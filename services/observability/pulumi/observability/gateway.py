"""Stable in-cluster gateway services for observability backends."""

import pulumi as p
import pulumi_kubernetes as k8s


def create_loki_gateway_service(
    loki: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> k8s.core.v1.Service:
    return k8s.core.v1.Service(
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
) -> k8s.core.v1.Service:
    return k8s.core.v1.Service(
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


def service_http_url(
    service: k8s.core.v1.Service,
    path: str = '',
) -> p.Output[str]:
    return p.Output.concat(
        'http://',
        service.metadata.name,
        '.',
        service.metadata.namespace,
        '.svc.cluster.local',
        path,
    )
