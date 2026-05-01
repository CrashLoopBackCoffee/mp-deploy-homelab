"""Loki log aggregation deployment."""

import pulumi as p
import pulumi_kubernetes as k8s

from observability.constants import GRAFANA_CHART_URL
from observability.model import ComponentConfig


def create_loki(
    component_config: ComponentConfig,
    *,
    k8s_opts: p.ResourceOptions,
) -> k8s.helm.v3.Release:
    return k8s.helm.v3.Release(
        'loki',
        chart='loki',
        version=component_config.loki.version,
        repository_opts={'repo': GRAFANA_CHART_URL},
        values={
            'deploymentMode': 'SingleBinary',
            'loki': {
                'auth_enabled': False,
                'commonConfig': {
                    'replication_factor': 1,
                },
                'storage': {
                    'type': 'filesystem',
                },
                'useTestSchema': True,
            },
            'singleBinary': {
                'replicas': 1,
                'persistence': {
                    'enabled': False,
                },
                'extraVolumes': [
                    {
                        'name': 'loki-data',
                        'emptyDir': {},
                    }
                ],
                'extraVolumeMounts': [
                    {
                        'name': 'loki-data',
                        'mountPath': '/var/loki',
                    }
                ],
            },
            # Disable distributed mode components
            'backend': {'replicas': 0},
            'read': {'replicas': 0},
            'write': {'replicas': 0},
            # Disable extras not needed in this phase
            'monitoring': {
                'selfMonitoring': {
                    'enabled': False,
                    'grafanaAgent': {'installOperator': False},
                },
            },
            'lokiCanary': {'enabled': False},
            'test': {'enabled': False},
            'minio': {'enabled': False},
        },
        opts=k8s_opts,
    )
