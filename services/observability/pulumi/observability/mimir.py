"""Mimir metrics storage deployment."""

import pulumi as p
import pulumi_kubernetes as k8s

from observability.constants import GRAFANA_CHART_URL
from observability.model import ComponentConfig


def create_mimir(
    component_config: ComponentConfig,
    *,
    k8s_opts: p.ResourceOptions,
) -> k8s.helm.v3.Release:
    retention_period = f'{component_config.mimir.retention_days}d'

    return k8s.helm.v3.Release(
        'mimir',
        chart='mimir-distributed',
        version=component_config.mimir.version,
        repository_opts={'repo': GRAFANA_CHART_URL},
        values={
            'mimir': {
                'structuredConfig': {
                    'multitenancy_enabled': False,
                    'common': {
                        'storage': {
                            'backend': 'filesystem',
                        },
                    },
                    'blocks_storage': {
                        'backend': 'filesystem',
                        'bucket_store': {
                            'sync_dir': '/data/tsdb-sync',
                        },
                        'filesystem': {
                            'dir': '/data/blocks-storage',
                        },
                        'tsdb': {
                            'dir': '/data/ingester-tsdb',
                        },
                    },
                    'ingester': {
                        'ring': {
                            'replication_factor': 1,
                        },
                    },
                    'limits': {
                        'compactor_blocks_retention_period': retention_period,
                    },
                    'compactor': {
                        'data_dir': '/data/compactor',
                    },
                    'alertmanager': {
                        'data_dir': '/data/alertmanager-data',
                    },
                    'alertmanager_storage': {
                        'backend': 'filesystem',
                        'filesystem': {
                            'dir': '/data/alertmanager-storage',
                        },
                    },
                    'ruler': {
                        'rule_path': '/data/ruler-rule-path',
                    },
                    'ruler_storage': {
                        'backend': 'filesystem',
                        'filesystem': {
                            'dir': '/data/ruler-storage',
                        },
                    },
                    'store_gateway': {
                        'sharding_ring': {
                            'replication_factor': 1,
                        },
                    },
                },
            },
            # Single replica with no persistence for ephemeral phase
            'ingester': {
                'replicas': 1,
                'zoneAwareReplication': {'enabled': False},
                'persistentVolume': {'enabled': False},
            },
            'store_gateway': {
                'replicas': 1,
                'zoneAwareReplication': {'enabled': False},
                'persistentVolume': {'enabled': False},
            },
            'minio': {'enabled': False},
            'compactor': {
                'persistentVolume': {'enabled': False},
            },
            'alertmanager': {
                'persistentVolume': {'enabled': False},
            },
        },
        opts=k8s_opts,
    )
