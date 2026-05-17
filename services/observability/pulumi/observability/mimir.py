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
    storage_class_name = component_config.mimir.storage_class_name

    return k8s.helm.v3.Release(
        'mimir',
        chart='mimir-distributed',
        version=component_config.mimir.version,
        repository_opts={'repo': GRAFANA_CHART_URL},
        values={
            'mimir': {
                'structuredConfig': {
                    'multitenancy_enabled': False,
                    'ingest_storage': {
                        'enabled': False,
                    },
                    'ingester': {
                        'push_grpc_method_enabled': True,
                        'ring': {
                            'replication_factor': 1,
                        },
                    },
                    'limits': {
                        'compactor_blocks_retention_period': retention_period,
                    },
                    'compactor': {
                        'data_dir': '/data',
                    },
                    'alertmanager': {
                        'data_dir': '/data',
                    },
                    'ruler': {
                        'rule_path': '/data',
                    },
                    'store_gateway': {
                        'sharding_ring': {
                            'replication_factor': 1,
                        },
                    },
                },
            },
            # Single-node deployment with retained local PVCs for cache/WAL data.
            'ingester': {
                'replicas': 1,
                'zoneAwareReplication': {'enabled': False},
                'persistentVolume': {
                    'enabled': True,
                    'size': f'{component_config.mimir.ingester_storage_size_gb}Gi',
                    'storageClass': storage_class_name,
                    'enableRetentionPolicy': True,
                    'whenDeleted': 'Retain',
                    'whenScaled': 'Retain',
                },
            },
            'store_gateway': {
                'replicas': 1,
                'zoneAwareReplication': {'enabled': False},
                'persistentVolume': {
                    'enabled': True,
                    'size': f'{component_config.mimir.store_gateway_storage_size_gb}Gi',
                    'storageClass': storage_class_name,
                    'enableRetentionPolicy': True,
                    'whenDeleted': 'Retain',
                    'whenScaled': 'Retain',
                },
            },
            'kafka': {'enabled': False},
            'minio': {
                'enabled': True,
                'mode': 'standalone',
                'replicas': 1,
                'drivesPerNode': 1,
                'buckets': [
                    {
                        'name': 'mimir-tsdb',
                        'policy': 'none',
                        'purge': False,
                    },
                    {
                        'name': 'mimir-ruler',
                        'policy': 'none',
                        'purge': False,
                    },
                ],
                'persistence': {
                    'storageClass': storage_class_name,
                    'size': f'{component_config.mimir.minio_storage_size_gb}Gi',
                },
            },
            'rollout_operator': {'enabled': False},
            'compactor': {
                'persistentVolume': {
                    'enabled': True,
                    'size': f'{component_config.mimir.compactor_storage_size_gb}Gi',
                    'storageClass': storage_class_name,
                    'enableRetentionPolicy': True,
                    'whenDeleted': 'Retain',
                    'whenScaled': 'Retain',
                },
            },
            'alertmanager': {
                'persistentVolume': {
                    'enabled': True,
                    'size': f'{component_config.mimir.alertmanager_storage_size_gb}Gi',
                    'storageClass': storage_class_name,
                    'enableRetentionPolicy': True,
                    'whenDeleted': 'Retain',
                    'whenScaled': 'Retain',
                },
            },
        },
        opts=k8s_opts,
    )
