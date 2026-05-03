"""kube-state-metrics deployment."""

import pulumi as p
import pulumi_kubernetes as k8s

from observability.constants import PROMETHEUS_COMMUNITY_CHART_URL
from observability.model import ComponentConfig

KUBE_STATE_METRICS_SERVICE_NAME = 'kube-state-metrics'
KUBE_STATE_METRICS_PORT = 8080


def create_kube_state_metrics(
    component_config: ComponentConfig,
    *,
    k8s_opts: p.ResourceOptions,
) -> k8s.helm.v3.Release:
    kube_state_metrics = k8s.helm.v3.Release(
        'kube-state-metrics',
        chart='kube-state-metrics',
        version=component_config.kube_state_metrics.version,
        repository_opts={'repo': PROMETHEUS_COMMUNITY_CHART_URL},
        values={
            'prometheusScrape': False,
        },
        opts=k8s_opts,
    )

    create_kube_state_metrics_service(kube_state_metrics, k8s_opts)

    return kube_state_metrics


def create_kube_state_metrics_service(
    kube_state_metrics: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> None:
    k8s.core.v1.Service(
        KUBE_STATE_METRICS_SERVICE_NAME,
        metadata={'name': KUBE_STATE_METRICS_SERVICE_NAME},
        spec={
            'selector': {
                'app.kubernetes.io/instance': kube_state_metrics.status.name,
                'app.kubernetes.io/name': 'kube-state-metrics',
            },
            'ports': [
                {
                    'name': 'http',
                    'port': KUBE_STATE_METRICS_PORT,
                    'target_port': 'http',
                },
            ],
        },
        opts=k8s_opts,
    )
