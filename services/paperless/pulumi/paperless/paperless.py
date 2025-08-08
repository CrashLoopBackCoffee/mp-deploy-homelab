import base64
import pathlib

import jinja2
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

    config, config_secret = create_configurations(component_config, fqdn, k8s_opts)

    sidecar_containers = []
    sidecar_volumes = []

    if component_config.rclone:
        sidecar_containers, sidecar_volumes = create_rclone_originals_sidecar(
            component_config, k8s_opts
        )

    paperless_sts = create_application_sts(
        component_config,
        config,
        config_secret,
        sidecar_containers,
        sidecar_volumes,
        k8s_opts,
    )

    create_service(fqdn if not tunneled else None, paperless_sts, k8s_opts)


def create_configurations(
    component_config: ComponentConfig,
    fqdn: p.Input[str],
    k8s_opts: p.ResourceOptions,
):
    admin_username = 'admin'
    admin_password = random.RandomPassword('admin-password', length=64, special=False).result

    p.export('admin-username', admin_username)
    p.export('admin-password', admin_password)

    if smtp := component_config.paperless.smtp:
        smtp_data = {
            'PAPERLESS_EMAIL_HOST': smtp.host,
            'PAPERLESS_EMAIL_PORT': str(smtp.port),
            'PAPERLESS_EMAIL_FROM': smtp.email,
            'PAPERLESS_EMAIL_HOST_USER': smtp.email,
            'PAPERLESS_EMAIL_HOST_PASSWORD': smtp.password.value,
            'PAPERLESS_EMAIL_USE_TLS': str(smtp.use_tls).lower(),
            'PAPERLESS_EMAIL_USE_SSL': str(smtp.use_ssl).lower(),
        }
    else:
        smtp_data = {}

    config = k8s.core.v1.ConfigMap(
        'config',
        data={
            'PAPERLESS_REDIS': f'redis://localhost:{component_config.redis.port}',
            'PAPERLESS_URL': p.Output.concat('https://', fqdn),
            'PAPERLESS_PORT': str(component_config.paperless.port),
            'PAPERLESS_ADMIN_USER': admin_username,
            'PAPERLESS_APPS': ','.join(('allauth.socialaccount.providers.openid_connect',)),
            'PAPERLESS_CONSUMER_POLLING': '30',
            'PAPERLESS_ACCOUNT_EMAIL_VERIFICATION': 'optional' if smtp else 'none',
            'PAPERLESS_ACCOUNT_ALLOW_SIGNUPS': 'false',
            'PAPERLESS_CONSUMER_RECURSIVE': 'true',
            'PAPERLESS_CONSUMER_ENABLE_BARCODES': 'true',
            'PAPERLESS_CONSUMER_BARCODE_SCANNER': 'ZXING',
            'PAPERLESS_CONSUMER_ENABLE_ASN_BARCODE': 'true',
            'PAPERLESS_CONSUMER_BARCODE_MAX_PAGES': '1',
        }
        | smtp_data,
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
        },
        type='Opaque',
        opts=k8s_opts,
    )

    return config, config_secret


def create_rclone_originals_sidecar(
    component_config: ComponentConfig,
    k8s_opts: p.ResourceOptions,
) -> tuple[
    list[k8s.core.v1.ContainerArgsDict],
    list[k8s.core.v1.VolumeArgsDict],
]:
    assert component_config.rclone, 'only called if configured'

    # to sync originals to a cloud drive, set up an rclone sidecar, mounting the media folder:
    rclone_config_file_name = 'rclone.conf'
    rclone_config_dir_readonly = '/config/rclone-read-only'
    rclone_config_dir_write = '/config/rclone'
    rclone_media_mount = '/mnt/paperless/media'
    rclone_script_name = 'rclone-sync.sh'

    rclone_script = k8s.core.v1.ConfigMap(
        rclone_script_name,
        data={
            rclone_script_name: jinja2.Template(
                pathlib.Path('assets/rclone-sync.sh').read_text(),
                undefined=jinja2.StrictUndefined,
            ).render(
                component_config.rclone.model_dump()
                | {
                    'rclone_config_file_name': rclone_config_file_name,
                    'rclone_config_dir_readonly': rclone_config_dir_readonly,
                    'rclone_config_dir_write': rclone_config_dir_write,
                    'rclone_media_mount': rclone_media_mount,
                }
            ),
        },
        opts=k8s_opts,
    )

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
        ),
        k8s.core.v1.VolumeArgsDict(
            name='rclone-script',
            config_map={
                'name': rclone_script.metadata.name,
                'items': [
                    {
                        'key': rclone_script_name,
                        'path': rclone_script_name,
                        'mode': 0o755,
                    }
                ],
            },
        ),
    ]

    init_containers = [
        k8s.core.v1.ContainerArgsDict(
            name='rclone',
            image=f'rclone/rclone:{component_config.rclone.version[1:]}',
            restart_policy='Always',
            volume_mounts=[
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
                {
                    'name': 'rclone-script',
                    'mount_path': '/scripts',
                    'read_only': True,
                },
            ],
            command=['/bin/sh', '/scripts/rclone-sync.sh'],
        )
    ]

    return init_containers, volumes


def create_application_sts(
    component_config: ComponentConfig,
    config: k8s.core.v1.ConfigMap,
    config_secret: k8s.core.v1.Secret,
    sidecar_containers: list[k8s.core.v1.ContainerArgsDict],
    sidecar_volumes: list[k8s.core.v1.VolumeArgsDict],
    k8s_opts: p.ResourceOptions,
) -> k8s.apps.v1.StatefulSet:
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
                            'readiness_probe': {
                                'http_get': {
                                    'port': 'http',
                                    'path': '/api/health',
                                }
                            },
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
                            'readiness_probe': {
                                'exec_': {
                                    'command': ['redis-cli', 'ping'],
                                },
                            },
                        },
                    ],
                    'init_containers': sidecar_containers,
                    'volumes': sidecar_volumes,
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

    kubectl_args = p.Output.concat(
        'exec statefulset/',
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
                                    'image': f'registry.k8s.io/kubectl:{component_config.paperless.exporter_kubectl_version}',
                                    'args': kubectl_args.apply(lambda a: a.split(' ')),
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
