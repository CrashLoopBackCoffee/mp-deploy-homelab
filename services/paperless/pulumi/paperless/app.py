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
    namespaced_provider: k8s.Provider,
):
    k8s_opts = p.ResourceOptions(provider=namespaced_provider)

    config, config_secret = configure(component_config, fqdn, k8s_opts)
    paperless_sts = deploy(component_config, config, config_secret, k8s_opts)
    expose(fqdn, paperless_sts, k8s_opts)


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
    # we use prod samba storage regardless of what kind of stack this currently is:
    samba_stack = p.StackReference(f'{p.get_organization()}/samba/prod')
    samba_fqdn = samba_stack.get_output('fqdn')

    smb_secret = k8s.core.v1.Secret(
        'smb-secret',
        string_data={
            'username': samba_stack.get_output('smb-k8s-username'),
            'password': samba_stack.get_output('smb-k8s-password'),
        },
        opts=k8s_opts,
    )

    def verify_share_names(existing_shares):
        if component_config.paperless.consume_smb_share not in existing_shares:
            raise UnresolvedSmbShareError(
                'Consume share does not exist.',
                component_config.paperless.consume_smb_share,
            )

        if component_config.paperless.media_smb_share not in existing_shares:
            raise UnresolvedSmbShareError(
                'Media share does not exist.',
                component_config.paperless.media_smb_share,
            )

    samba_stack.get_output('smb-shares').apply(verify_share_names)

    consume_storage_class = _create_smb_storage_class(
        component_config.paperless.consume_smb_share,
        samba_fqdn=samba_fqdn,
        share=component_config.paperless.consume_smb_share,
        reclaim_policy='Delete',
        smb_secret=smb_secret,
        k8s_opts=k8s_opts,
    )

    media_storage_class = _create_smb_storage_class(
        component_config.paperless.media_smb_share,
        samba_fqdn=samba_fqdn,
        share=component_config.paperless.media_smb_share,
        reclaim_policy='Retain',
        smb_secret=smb_secret,
        k8s_opts=k8s_opts,
    )

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
                        'storage_class_name': media_storage_class.metadata.name,
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
                        'storage_class_name': consume_storage_class.metadata.name,
                        'access_modes': ['ReadWriteOnce'],
                        'resources': {
                            'requests': {
                                'storage': f'{component_config.paperless.consume_size_mb}Mi'
                            }
                        },
                    },
                },
            ],
        },
        opts=k8s_opts,
    )

    export_command = p.Output.concat(
        'kubectl exec statefulset/', sts.metadata.name, ' -c webserver -- python manage.py help'
    )

    k8s.batch.v1.CronJob(
        'exporter',
        metadata={'name': 'exporter'},
        spec={
            'schedule': '* * * * *',
            'successful_jobs_history_limit': 2,
            'job_template': {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'exporter',
                                    'image': 'bitnami/kubectl:latest',
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


def _create_smb_storage_class(
    name: str,
    *,
    samba_fqdn: p.Input[str],
    share: str,
    reclaim_policy: str,
    smb_secret: k8s.core.v1.Secret,
    k8s_opts: p.ResourceOptions,
) -> k8s.storage.v1.StorageClass:
    return k8s.storage.v1.StorageClass(
        name,
        metadata={
            'name': name,
        },
        provisioner='smb.csi.k8s.io',
        parameters={
            'source': p.Output.concat('//', samba_fqdn, '/', share),
            # if csi.storage.k8s.io/provisioner-secret is provided, will create a sub directory
            # with PV name under source
            'csi.storage.k8s.io/provisioner-secret-name': smb_secret.metadata.name,
            'csi.storage.k8s.io/provisioner-secret-namespace': smb_secret.metadata.namespace,
            'csi.storage.k8s.io/node-stage-secret-name': smb_secret.metadata.name,
            'csi.storage.k8s.io/node-stage-secret-namespace': smb_secret.metadata.namespace,
        },
        reclaim_policy=reclaim_policy,
        volume_binding_mode='Immediate',
        mount_options=[
            'uid=1000',
            'gid=1000',
            'file_mode=0664',
            'dir_mode=0775',
            'iocharset=utf8',
        ],
        opts=k8s_opts,
    )


def expose(fqdn, paperless_sts, k8s_opts):
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
