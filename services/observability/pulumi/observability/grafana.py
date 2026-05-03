"""Grafana dashboard deployment."""

import pathlib

import pulumi as p
import pulumi_kubernetes as k8s
import pulumi_random as random

from observability.constants import GRAFANA_CHART_URL
from observability.gateway import service_http_url
from observability.model import ComponentConfig

GRAFANA_SECRET_KEY_SECRET_NAME = 'grafana-secret-key'
GRAFANA_SECRET_KEY_SECRET_KEY = 'secret-key'
GRAFANA_DATA_PVC_NAME = 'grafana-data'
GRAFANA_BACKUP_PVC_NAME = 'grafana-backup'
GRAFANA_BACKUP_SCRIPT = pathlib.Path('assets/grafana-backup.py').read_text()


def create_grafana(
    component_config: ComponentConfig,
    *,
    loki_gateway: k8s.core.v1.Service,
    mimir_gateway: k8s.core.v1.Service,
    k8s_opts: p.ResourceOptions,
) -> k8s.helm.v3.Release:
    admin_username = 'admin'
    admin_password = (
        component_config.grafana.admin_password
        or random.RandomPassword(
            'grafana-admin-password',
            length=64,
            special=False,
        ).result
    )

    secret_key = random.RandomPassword(
        'grafana-secret-key',
        length=64,
        special=False,
    ).result

    protected_k8s_opts = p.ResourceOptions.merge(
        k8s_opts,
        p.ResourceOptions(protect=p.get_stack().startswith('prod')),
    )

    secret_key_secret = k8s.core.v1.Secret(
        GRAFANA_SECRET_KEY_SECRET_NAME,
        metadata={'name': GRAFANA_SECRET_KEY_SECRET_NAME},
        string_data={GRAFANA_SECRET_KEY_SECRET_KEY: secret_key},
        type='Opaque',
        opts=protected_k8s_opts,
    )

    data_pvc = k8s.core.v1.PersistentVolumeClaim(
        GRAFANA_DATA_PVC_NAME,
        metadata={'name': GRAFANA_DATA_PVC_NAME},
        spec={
            'access_modes': ['ReadWriteOnce'],
            'storage_class_name': component_config.grafana.storage_class_name,
            'resources': {'requests': {'storage': f'{component_config.grafana.storage_size_gb}Gi'}},
        },
        opts=protected_k8s_opts,
    )

    if component_config.grafana.backup_enabled:
        create_grafana_backup(
            component_config,
            data_pvc=data_pvc,
            secret_key_secret=secret_key_secret,
            k8s_opts=k8s_opts,
            protected_k8s_opts=protected_k8s_opts,
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
            'envValueFrom': {
                'GF_SECURITY_SECRET_KEY': {
                    'secretKeyRef': {
                        'name': secret_key_secret.metadata.name,
                        'key': GRAFANA_SECRET_KEY_SECRET_KEY,
                    },
                },
            },
            'initChownData': {'enabled': False},
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
    p.export(
        'grafana-secret-key-backup-path',
        p.Output.concat(
            'k8s://Secret/',
            secret_key_secret.metadata.namespace,
            '/',
            secret_key_secret.metadata.name,
            '#',
            GRAFANA_SECRET_KEY_SECRET_KEY,
        ),
    )

    return grafana


def create_grafana_backup(
    component_config: ComponentConfig,
    *,
    data_pvc: k8s.core.v1.PersistentVolumeClaim,
    secret_key_secret: k8s.core.v1.Secret,
    k8s_opts: p.ResourceOptions,
    protected_k8s_opts: p.ResourceOptions,
) -> None:
    backup_pvc = k8s.core.v1.PersistentVolumeClaim(
        GRAFANA_BACKUP_PVC_NAME,
        metadata={'name': GRAFANA_BACKUP_PVC_NAME},
        spec={
            'access_modes': ['ReadWriteOnce'],
            'storage_class_name': component_config.grafana.backup_storage_class_name,
            'resources': {
                'requests': {'storage': f'{component_config.grafana.backup_storage_size_gb}Gi'}
            },
        },
        opts=protected_k8s_opts,
    )

    k8s.batch.v1.CronJob(
        GRAFANA_BACKUP_PVC_NAME,
        metadata={'name': GRAFANA_BACKUP_PVC_NAME},
        spec={
            'schedule': component_config.grafana.backup_schedule,
            'concurrency_policy': 'Forbid',
            'successful_jobs_history_limit': 3,
            'failed_jobs_history_limit': 3,
            'job_template': {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'backup',
                                    'image': (
                                        'docker.io/library/python:'
                                        f'{component_config.grafana.backup_python_version}'
                                    ),
                                    'command': ['python', '-c', GRAFANA_BACKUP_SCRIPT],
                                    'volume_mounts': [
                                        {
                                            'name': 'grafana-data',
                                            'mount_path': '/source/grafana',
                                            'read_only': True,
                                        },
                                        {
                                            'name': 'backup',
                                            'mount_path': '/backup',
                                        },
                                        {
                                            'name': 'secret-key',
                                            'mount_path': '/source/secrets',
                                            'read_only': True,
                                        },
                                    ],
                                }
                            ],
                            'volumes': [
                                {
                                    'name': 'grafana-data',
                                    'persistent_volume_claim': {
                                        'claim_name': data_pvc.metadata.name,
                                        'read_only': True,
                                    },
                                },
                                {
                                    'name': 'backup',
                                    'persistent_volume_claim': {
                                        'claim_name': backup_pvc.metadata.name
                                    },
                                },
                                {
                                    'name': 'secret-key',
                                    'secret': {
                                        'secret_name': secret_key_secret.metadata.name,
                                        'items': [
                                            {
                                                'key': GRAFANA_SECRET_KEY_SECRET_KEY,
                                                'path': GRAFANA_SECRET_KEY_SECRET_KEY,
                                            }
                                        ],
                                    },
                                },
                            ],
                            'restart_policy': 'OnFailure',
                        }
                    }
                },
            },
        },
        opts=k8s_opts,
    )
