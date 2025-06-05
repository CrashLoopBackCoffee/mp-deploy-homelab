import base64

import pulumi as p
import pulumi_kubernetes as k8s
import pulumi_random as random

from paperless.model import ComponentConfig

LABELS = {'app': 'paperless'}


class UnresolvedSmbShareError(Exception):
    """The refereced share does not exist."""


def create_paperless(
    component_config: ComponentConfig,
    fqdn: p.Input[str],
    tunneled: bool,
    namespaced_provider: k8s.Provider,
):
    k8s_opts = p.ResourceOptions(provider=namespaced_provider)

    config, config_secret = configure(component_config, fqdn, k8s_opts)
    paperless_sts = deploy(component_config, config, config_secret, k8s_opts)
    create_service(fqdn if not tunneled else None, paperless_sts, k8s_opts)


def configure(
    component_config: ComponentConfig,
    fqdn: p.Input[str],
    k8s_opts: p.ResourceOptions,
):
    admin_username = 'admin'
    admin_password = random.RandomPassword('admin-password', length=64, special=False).result

    p.export('admin-username', admin_username)
    p.export('admin-password', admin_password)

    config = k8s.core.v1.ConfigMap(
        'config',
        data={
            'PAPERLESS_REDIS': f'redis://localhost:{component_config.redis.port}',
            'PAPERLESS_URL': p.Output.concat('https://', fqdn),
            'PAPERLESS_PORT': str(component_config.paperless.port),
            'PAPERLESS_ADMIN_USER': admin_username,
            'PAPERLESS_APPS': ','.join(('allauth.socialaccount.providers.openid_connect',)),
            'PAPERLESS_CONSUMER_POLLING': '30',
            'PAPERLESS_ACCOUNT_EMAIL_VERIFICATION': 'none',
            'PAPERLESS_CONSUMER_RECURSIVE': 'true',
            'PAPERLESS_CONSUMER_ENABLE_BARCODES': 'true',
            'PAPERLESS_CONSUMER_BARCODE_SCANNER': 'ZXING',
            'PAPERLESS_CONSUMER_ENABLE_ASN_BARCODE': 'true',
            'PAPERLESS_CONSUMER_BARCODE_MAX_PAGES': '1',
        },
        opts=k8s_opts,
    )

    config_secret = k8s.core.v1.Secret(
        'config-secret',
        string_data={
            'PAPERLESS_SECRET_KEY': random.RandomPassword(
                'paperless-secret-key',
                length=64,
                special=False,
            ).result,
            'PAPERLESS_ADMIN_PASSWORD': admin_password,
            # Entra ID OIDC config contains client secret:
            'PAPERLESS_SOCIALACCOUNT_PROVIDERS': p.Output.json_dumps(
                {
                    'openid_connect': {
                        'APPS': [
                            {
                                'provider_id': 'microsoft',
                                'name': 'Microsoft Entra ID',
                                'client_id': component_config.entraid.client_id,
                                'secret': component_config.entraid.client_secret,
                                'settings': {
                                    'server_url': p.Output.concat(
                                        'https://login.microsoftonline.com/',
                                        component_config.entraid.tenant_id,
                                        '/v2.0',
                                    ),
                                    'authorization_url': p.Output.concat(
                                        'https://login.microsoftonline.com/',
                                        component_config.entraid.tenant_id,
                                        '/oauth2/v2.0/authorize',
                                    ),
                                    'access_token_url': p.Output.concat(
                                        'https://login.microsoftonline.com/',
                                        component_config.entraid.tenant_id,
                                        '/oauth2/v2.0/token',
                                    ),
                                    'userinfo_url': 'https://graph.microsoft.com/oidc/userinfo',
                                    'jwks_uri': p.Output.concat(
                                        'https://login.microsoftonline.com/',
                                        component_config.entraid.tenant_id,
                                        '/discovery/v2.0/keys',
                                    ),
                                    'scope': ['openid', 'email', 'profile'],
                                    'extra_data': ['email', 'name', 'preferred_username'],
                                },
                            }
                        ]
                    }
                }
            ),
        },
        type='Opaque',
        opts=k8s_opts,
    )

    return config, config_secret


def deploy(
    component_config: ComponentConfig,
    config: k8s.core.v1.ConfigMap,
    config_secret: k8s.core.v1.Secret,
    k8s_opts: p.ResourceOptions,
) -> k8s.apps.v1.StatefulSet:
    # TODO Refactor split between config and deploy.

    if component_config.rclone:
        # to sync originals to a cloud drive, set up an rclone sidecar, mounting the media folder:
        rclone_config_file_name = 'rclone.conf'
        rclone_config_dir_readonly = '/config/rclone-read-only'
        rclone_config_dir_write = '/config/rclone'
        rclone_media_mount = '/mnt/paperless/media'

        rclone_conf = k8s.core.v1.Secret(
            'rclone-conf',
            string_data={
                rclone_config_file_name: component_config.rclone.rclone_conf_b64.value.apply(
                    lambda v: base64.b64decode(v.encode()).decode()
                ),
            },
            type='Opaque',
            opts=k8s_opts,
        )

        volumes = [
            k8s.core.v1.VolumeArgsDict(
                name='rclone-conf',
                secret={
                    'secret_name': rclone_conf.metadata.name,
                    'items': [
                        {
                            'key': rclone_config_file_name,
                            'path': rclone_config_file_name,
                        }
                    ],
                },
            )
        ]

        init_containers = [
            k8s.core.v1.ContainerArgsDict(
                {
                    'name': 'rclone',
                    'image': f'rclone/rclone:{component_config.rclone.version[1:]}',
                    'restart_policy': 'Always',
                    'volume_mounts': [
                        {
                            'name': 'rclone-conf',
                            'mount_path': rclone_config_dir_readonly,
                        },
                        {
                            'name': 'media',
                            'mount_path': rclone_media_mount,
                            'read_only': True,
                            'recursive_read_only': 'IfPossible',
                        },
                    ],
                    'command': [
                        'sh',
                        '-c',
                        f'mkdir -p {rclone_config_dir_write}; '
                        f'cat {rclone_config_dir_readonly}/{rclone_config_file_name} > {rclone_config_dir_write}/{rclone_config_file_name}; '
                        'while true; '
                        f'do rclone sync {rclone_media_mount}/documents/originals {component_config.rclone.destination} '
                        f'--config {rclone_config_dir_write}/{rclone_config_file_name} -v; '
                        f'sleep {component_config.rclone.sync_period_sec}; '
                        'done',
                    ],
                }
            )
        ]
    else:
        volumes = []
        init_containers = []

    sts = k8s.apps.v1.StatefulSet(
        'paperless',
        metadata={'name': 'paperless'},
        spec={
            'replicas': 1,
            'selector': {
                'match_labels': LABELS,
            },
            # we omit a headless service since we don't need cluster-internal network name identity:
            'service_name': '',
            'template': {
                'metadata': {
                    'labels': LABELS,
                },
                'spec': {
                    'containers': [
                        {
                            'name': 'webserver',
                            'image': f'ghcr.io/paperless-ngx/paperless-ngx:{component_config.paperless.version}',
                            'volume_mounts': [
                                {
                                    'name': 'data',
                                    'mount_path': '/usr/src/paperless/data',
                                },
                                {
                                    'name': 'media',
                                    'mount_path': '/usr/src/paperless/media',
                                },
                                {
                                    'name': 'consume',
                                    'mount_path': '/usr/src/paperless/consume',
                                },
                                {
                                    'name': 'export',
                                    'mount_path': '/usr/src/paperless/export',
                                },
                            ],
                            'ports': [
                                {
                                    'name': 'http',
                                    'container_port': component_config.paperless.port,
                                },
                            ],
                            'env_from': [
                                {
                                    'config_map_ref': {
                                        'name': config.metadata.name,
                                    }
                                },
                                {
                                    'secret_ref': {
                                        'name': config_secret.metadata.name,
                                    }
                                },
                            ],
                        },
                        {
                            'name': 'broker',
                            'image': f'docker.io/library/redis:{component_config.redis.version}',
                            'ports': [
                                {
                                    'name': 'redis',
                                    'container_port': component_config.redis.port,
                                },
                            ],
                        },
                    ],
                    'init_containers': init_containers,
                    'volumes': volumes,
                },
            },
            'volume_claim_templates': [
                {
                    'metadata': {
                        'name': 'data',
                    },
                    'spec': {
                        'storage_class_name': 'data-hostpath-retained',
                        'access_modes': ['ReadWriteOnce'],
                        'resources': {
                            'requests': {'storage': f'{component_config.paperless.data_size_gb}Gi'}
                        },
                    },
                },
                {
                    'metadata': {
                        'name': 'media',
                    },
                    'spec': {
                        'storage_class_name': 'samba-write-k8s',
                        'access_modes': ['ReadWriteOnce'],
                        'resources': {
                            'requests': {'storage': f'{component_config.paperless.media_size_gb}Gi'}
                        },
                    },
                },
                {
                    'metadata': {
                        'name': 'consume',
                    },
                    'spec': {
                        'storage_class_name': 'samba-write-all',
                        'access_modes': ['ReadWriteOnce'],
                        'resources': {
                            'requests': {
                                'storage': f'{component_config.paperless.consume_size_mb}Mi'
                            }
                        },
                    },
                },
                {
                    'metadata': {
                        'name': 'export',
                    },
                    'spec': {
                        'storage_class_name': 'samba-write-k8s',
                        'access_modes': ['ReadWriteOnce'],
                        'resources': {
                            'requests': {
                                'storage': f'{component_config.paperless.export_size_gb}Gi'
                            }
                        },
                    },
                },
            ],
        },
        opts=k8s_opts,
    )

    export_command = p.Output.concat(
        'kubectl exec statefulset/',
        sts.metadata.name,
        ' -c webserver -- '
        'document_exporter ../export --delete --use-filename-format --use-folder-prefix --no-progress-bar',
    )

    k8s.batch.v1.CronJob(
        'exporter',
        metadata={'name': 'exporter'},
        spec={
            'schedule': component_config.paperless.exporter_schedule,
            'successful_jobs_history_limit': 3,
            'job_template': {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'exporter',
                                    'image': f'bitnami/kubectl:{component_config.paperless.exporter_kubectl_version}',
                                    'command': ['/bin/sh', '-c', export_command],
                                }
                            ],
                            'restart_policy': 'Never',
                        }
                    }
                },
            },
        },
        opts=k8s_opts,
    )

    return sts


def create_service(fqdn, paperless_sts, k8s_opts):
    service = k8s.core.v1.Service(
        'paperless',
        metadata={
            'name': 'paperless',
        },
        spec={
            'selector': paperless_sts.spec.selector.match_labels,
            'ports': [
                {
                    'name': 'http',
                    'port': 80,
                    'target_port': 'http',
                },
            ],
        },
        opts=k8s_opts,
    )

    if fqdn:
        k8s.apiextensions.CustomResource(
            'ingress',
            api_version='traefik.io/v1alpha1',
            kind='IngressRoute',
            metadata={
                'name': 'ingress',
            },
            spec={
                'entryPoints': ['websecure'],
                'routes': [
                    {
                        'kind': 'Rule',
                        'match': p.Output.concat('Host(`', fqdn, '`)'),
                        'services': [
                            {
                                'name': service.metadata.name,
                                'namespace': service.metadata.namespace,
                                'port': 'http',
                            },
                        ],
                    }
                ],
                # use default wildcard certificate:
                'tls': {},
            },
            opts=k8s_opts,
        )
