"""External log ingestion endpoint."""

import pulumi as p
import pulumi_kubernetes as k8s
import pulumi_random as random

from observability.model import ComponentConfig

LOGS_INGEST_USERNAME = 'logger'
LOGS_PUSH_PATH = '/loki/api/v1/push'
LOGS_BASIC_AUTH_SECRET_NAME = 'logs-ingest-basic-auth'
LOGS_BASIC_AUTH_MIDDLEWARE_NAME = 'logs-ingest-basic-auth'


def create_logs_ingress(
    component_config: ComponentConfig,
    *,
    alloy_service: k8s.core.v1.Service,
    k8s_opts: p.ResourceOptions,
) -> None:
    password = random.RandomPassword(
        'logs-ingest-password',
        length=48,
        special=False,
    )

    basic_auth_secret = k8s.core.v1.Secret(
        LOGS_BASIC_AUTH_SECRET_NAME,
        metadata={'name': LOGS_BASIC_AUTH_SECRET_NAME},
        string_data={
            'users': p.Output.concat(LOGS_INGEST_USERNAME, ':', password.bcrypt_hash),
        },
        type='Opaque',
        opts=k8s_opts,
    )

    basic_auth_middleware = k8s.apiextensions.CustomResource(
        LOGS_BASIC_AUTH_MIDDLEWARE_NAME,
        api_version='traefik.io/v1alpha1',
        kind='Middleware',
        metadata={'name': LOGS_BASIC_AUTH_MIDDLEWARE_NAME},
        spec={
            'basicAuth': {
                'secret': basic_auth_secret.metadata.name,
            }
        },
        opts=k8s_opts,
    )

    k8s.apiextensions.CustomResource(
        'logs-ingest-ingress',
        api_version='traefik.io/v1alpha1',
        kind='IngressRoute',
        metadata={'name': 'logs-ingest-ingress'},
        spec={
            'entryPoints': ['websecure'],
            'routes': [
                {
                    'kind': 'Rule',
                    'match': p.Output.concat(
                        'Host(`', component_config.ingress.logs_hostname, '`)'
                    ),
                    'middlewares': [
                        {
                            'name': LOGS_BASIC_AUTH_MIDDLEWARE_NAME,
                        }
                    ],
                    'services': [
                        {
                            'name': alloy_service.metadata.name,
                            'namespace': alloy_service.metadata.namespace,
                            'port': 'loki-push',
                        },
                    ],
                },
            ],
            # use default wildcard certificate:
            'tls': {},
        },
        opts=p.ResourceOptions.merge(
            k8s_opts,
            p.ResourceOptions(depends_on=[basic_auth_middleware]),
        ),
    )

    p.export('logs-ingest-hostname', component_config.ingress.logs_hostname)
    p.export('logs-ingest-username', LOGS_INGEST_USERNAME)
    p.export('logs-ingest-password', password.result)
    p.export(
        'logs-ingest-url',
        p.Output.secret(
            p.Output.concat(
                'https://',
                LOGS_INGEST_USERNAME,
                ':',
                password.result,
                '@',
                component_config.ingress.logs_hostname,
                LOGS_PUSH_PATH,
            )
        ),
    )
