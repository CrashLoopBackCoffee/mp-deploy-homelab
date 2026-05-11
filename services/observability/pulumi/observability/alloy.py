"""Grafana Alloy OpenTelemetry gateway deployment."""

import pathlib

import jinja2
import pulumi as p
import pulumi_kubernetes as k8s

from observability.constants import GRAFANA_CHART_URL
from observability.gateway import service_http_url
from observability.model import ComponentConfig, StaticScrapeTarget

ALLOY_SERVICE_NAME = 'alloy'
ALLOY_OTLP_GRPC_PORT = 4317
ALLOY_OTLP_HTTP_PORT = 4318
ALLOY_LOKI_PUSH_PORT = 3100
ALLOY_STATIC_SCRAPE_TARGET_SECRETS_NAME = 'alloy-static-scrape-target-secrets'
ALLOY_STATIC_SCRAPE_TARGET_SECRETS_VOLUME = 'static-scrape-target-secrets'
ALLOY_STATIC_SCRAPE_TARGET_SECRETS_PATH = '/etc/alloy/secrets/static-scrape-targets'


def create_alloy(
    component_config: ComponentConfig,
    *,
    loki_gateway: k8s.core.v1.Service,
    mimir_gateway: k8s.core.v1.Service,
    k8s_opts: p.ResourceOptions,
) -> tuple[k8s.helm.v3.Release, k8s.core.v1.Service]:
    static_scrape_target_secrets = create_static_scrape_target_secret(
        component_config.alloy.static_scrape_targets,
        k8s_opts,
    )

    alloy = k8s.helm.v3.Release(
        'alloy',
        chart='alloy',
        version=component_config.alloy.version,
        repository_opts={'repo': GRAFANA_CHART_URL},
        values={
            'controller': {
                'type': 'deployment',
                'replicas': 1,
                'volumes': {
                    'extra': alloy_static_scrape_target_secret_volumes(
                        static_scrape_target_secrets
                    ),
                },
            },
            'alloy': {
                'configMap': {
                    'content': create_alloy_config(
                        static_scrape_targets=component_config.alloy.static_scrape_targets,
                        loki_gateway=loki_gateway,
                        mimir_gateway=mimir_gateway,
                    ),
                },
                'mounts': {
                    'extra': alloy_static_scrape_target_secret_mounts(static_scrape_target_secrets),
                },
                'extraPorts': [
                    {
                        'name': 'otlp-grpc',
                        'port': ALLOY_OTLP_GRPC_PORT,
                        'targetPort': ALLOY_OTLP_GRPC_PORT,
                        'protocol': 'TCP',
                    },
                    {
                        'name': 'otlp-http',
                        'port': ALLOY_OTLP_HTTP_PORT,
                        'targetPort': ALLOY_OTLP_HTTP_PORT,
                        'protocol': 'TCP',
                    },
                    {
                        'name': 'loki-push',
                        'port': ALLOY_LOKI_PUSH_PORT,
                        'targetPort': ALLOY_LOKI_PUSH_PORT,
                        'protocol': 'TCP',
                    },
                ],
            },
        },
        opts=k8s_opts,
    )

    create_alloy_cluster_metrics_rbac(alloy, k8s_opts)
    service = create_alloy_gateway_service(alloy, k8s_opts)
    export_alloy_endpoints()

    return alloy, service


def create_static_scrape_target_secret(
    static_scrape_targets: list[StaticScrapeTarget],
    k8s_opts: p.ResourceOptions,
) -> k8s.core.v1.Secret | None:
    bearer_tokens = {
        f'{target.name}-bearer-token': target.bearer_token
        for target in static_scrape_targets
        if target.bearer_token is not None
    }

    if not bearer_tokens:
        return None

    return k8s.core.v1.Secret(
        ALLOY_STATIC_SCRAPE_TARGET_SECRETS_NAME,
        metadata={'name': ALLOY_STATIC_SCRAPE_TARGET_SECRETS_NAME},
        string_data=bearer_tokens,
        type='Opaque',
        opts=k8s_opts,
    )


def alloy_static_scrape_target_secret_volumes(
    secret: k8s.core.v1.Secret | None,
) -> list[dict[str, object]]:
    if secret is None:
        return []

    return [
        {
            'name': ALLOY_STATIC_SCRAPE_TARGET_SECRETS_VOLUME,
            'secret': {
                'secretName': secret.metadata.name,
            },
        }
    ]


def alloy_static_scrape_target_secret_mounts(
    secret: k8s.core.v1.Secret | None,
) -> list[dict[str, object]]:
    if secret is None:
        return []

    return [
        {
            'name': ALLOY_STATIC_SCRAPE_TARGET_SECRETS_VOLUME,
            'mountPath': ALLOY_STATIC_SCRAPE_TARGET_SECRETS_PATH,
            'readOnly': True,
        }
    ]


def create_alloy_config(
    *,
    static_scrape_targets: list[StaticScrapeTarget],
    loki_gateway: k8s.core.v1.Service,
    mimir_gateway: k8s.core.v1.Service,
) -> p.Output[str]:
    return p.Output.all(
        mimir_remote_write_url=service_http_url(mimir_gateway, '/api/v1/push'),
        loki_push_url=service_http_url(loki_gateway, '/loki/api/v1/push'),
        otlp_grpc_port=ALLOY_OTLP_GRPC_PORT,
        otlp_http_port=ALLOY_OTLP_HTTP_PORT,
        loki_push_port=ALLOY_LOKI_PUSH_PORT,
        static_scrape_target_secrets_path=ALLOY_STATIC_SCRAPE_TARGET_SECRETS_PATH,
        static_scrape_targets=static_scrape_targets,
    ).apply(
        lambda values: jinja2.Template(
            pathlib.Path('assets/alloy/config.alloy.j2').read_text(),
            undefined=jinja2.StrictUndefined,
        ).render(values)
    )


def create_alloy_cluster_metrics_rbac(
    alloy: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> None:
    cluster_role = k8s.rbac.v1.ClusterRole(
        'alloy-kubelet-proxy',
        metadata={'name': 'alloy-kubelet-proxy'},
        rules=[
            k8s.rbac.v1.PolicyRuleArgs(
                api_groups=[''],
                resources=['nodes/proxy'],
                verbs=['get'],
            ),
            k8s.rbac.v1.PolicyRuleArgs(
                non_resource_urls=['/metrics'],
                verbs=['get'],
            ),
        ],
        opts=k8s_opts,
    )

    k8s.rbac.v1.ClusterRoleBinding(
        'alloy-kubelet-proxy',
        metadata={'name': 'alloy-kubelet-proxy'},
        role_ref=k8s.rbac.v1.RoleRefArgs(
            api_group='rbac.authorization.k8s.io',
            kind='ClusterRole',
            name=cluster_role.metadata['name'],
        ),
        subjects=[
            k8s.rbac.v1.SubjectArgs(
                kind='ServiceAccount',
                name=alloy.status.name,
                namespace='observability',
            ),
        ],
        opts=k8s_opts,
    )


def create_alloy_gateway_service(
    alloy: k8s.helm.v3.Release,
    k8s_opts: p.ResourceOptions,
) -> k8s.core.v1.Service:
    return k8s.core.v1.Service(
        ALLOY_SERVICE_NAME,
        metadata={'name': ALLOY_SERVICE_NAME},
        spec={
            'selector': {
                'app.kubernetes.io/instance': alloy.status.name,
                'app.kubernetes.io/name': 'alloy',
            },
            'ports': [
                {
                    'name': 'otlp-grpc',
                    'port': ALLOY_OTLP_GRPC_PORT,
                    'target_port': 'otlp-grpc',
                },
                {
                    'name': 'otlp-http',
                    'port': ALLOY_OTLP_HTTP_PORT,
                    'target_port': 'otlp-http',
                },
                {
                    'name': 'loki-push',
                    'port': ALLOY_LOKI_PUSH_PORT,
                    'target_port': 'loki-push',
                },
            ],
        },
        opts=k8s_opts,
    )


def export_alloy_endpoints() -> None:
    p.export(
        'alloy-otlp-grpc-endpoint',
        f'{ALLOY_SERVICE_NAME}.observability.svc.cluster.local:{ALLOY_OTLP_GRPC_PORT}',
    )
    p.export(
        'alloy-otlp-http-endpoint',
        f'http://{ALLOY_SERVICE_NAME}.observability.svc.cluster.local:{ALLOY_OTLP_HTTP_PORT}',
    )
    p.export(
        'alloy-loki-push-endpoint',
        f'http://{ALLOY_SERVICE_NAME}.observability.svc.cluster.local:{ALLOY_LOKI_PUSH_PORT}',
    )
