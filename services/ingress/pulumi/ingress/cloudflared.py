import base64

import pulumi as p
import pulumi_cloudflare as cloudflare
import pulumi_kubernetes as k8s
import pulumi_random

from ingress.model import ComponentConfig


def create_cloudflared(
    component_config: ComponentConfig,
    k8s_provider: k8s.Provider,
    cloudflare_provider: cloudflare.Provider,
):
    ns = k8s.core.v1.Namespace(
        'cloudflared',
        metadata={'name': 'cloudflared'},
        opts=p.ResourceOptions(provider=k8s_provider),
    )

    namespaced_k8s_provider = k8s.Provider(
        'cloudflared-provider',
        kubeconfig=k8s_provider.kubeconfig,  # pyright: ignore[reportAttributeAccessIssue]
        namespace=ns.metadata['name'],
    )
    k8s_opts = p.ResourceOptions(provider=namespaced_k8s_provider)

    cloudflare_opts = p.ResourceOptions(provider=cloudflare_provider)
    cloudflare_invoke_opts = p.InvokeOptions(provider=cloudflare_provider)

    # create cloudflared tunnel:
    cloudflare_accounts = cloudflare.get_accounts_output(opts=cloudflare_invoke_opts)
    cloudflare_account_id = cloudflare_accounts.results.apply(lambda results: results[0].id)
    tunnel_password = pulumi_random.RandomPassword('cloudflared', length=64)
    tunnel = cloudflare.ZeroTrustTunnelCloudflared(
        'tunnel',
        account_id=cloudflare_account_id,
        name='cloudflared-k8s',
        tunnel_secret=tunnel_password.result.apply(lambda p: base64.b64encode(p.encode()).decode()),
        config_src='cloudflare',
        opts=cloudflare_opts,
    )

    # get tunnel token and store in secret:
    tunnel_token = cloudflare.get_zero_trust_tunnel_cloudflared_token_output(
        account_id=cloudflare_account_id, tunnel_id=tunnel.id, opts=cloudflare_invoke_opts
    )

    secret = k8s.core.v1.Secret(
        'cloudflared',
        string_data={
            'token': tunnel_token.token,
        },
        opts=k8s_opts,
    )

    # deploy cloudflared:
    app_labels = {'app': 'cloudflared'}
    k8s.apps.v1.Deployment(
        'cloudflared',
        metadata={
            'name': 'cloudflared',
        },
        spec={
            'selector': {'match_labels': app_labels},
            'replicas': 1,
            'template': {
                'metadata': {'labels': app_labels},
                'spec': {
                    'containers': [
                        {
                            'name': 'cloudflared',
                            'image': f'cloudflare/cloudflared:{component_config.cloudflared.version}',
                            'args': [
                                'tunnel',
                                '--no-autoupdate',
                                'run',
                            ],
                            'env': [
                                {
                                    'name': 'TUNNEL_TOKEN',
                                    'value_from': {
                                        'secret_key_ref': {
                                            'name': secret.metadata.name,
                                            'key': 'token',
                                        }
                                    },
                                },
                                {
                                    'name': 'TUNNEL_METRICS',
                                    'value': '0.0.0.0:8080',
                                },
                            ],
                            'readiness_probe': {
                                'http_get': {
                                    'path': '/ready',
                                    'port': 8080,
                                },
                                'timeout_seconds': 5,
                                'success_threshold': 1,
                                'failure_threshold': 3,
                            },
                        }
                    ],
                },
            },
        },
        opts=k8s_opts,
    )

    ingress_rules = []
    for ingress in component_config.cloudflared.ingress:
        rule: cloudflare.ZeroTrustTunnelCloudflaredConfigConfigIngressArgsDict = {
            'service': ingress.service,
            'hostname': ingress.hostname,
        }
        if ingress.origin_server_name:
            rule['origin_request'] = {'origin_server_name': ingress.origin_server_name}

        ingress_rules.append(rule)

    cloudflare.ZeroTrustTunnelCloudflaredConfig(
        'cloudflared',
        account_id=cloudflare_account_id,
        tunnel_id=tunnel.id,
        config={
            'ingresses': [
                *ingress_rules,
                # catch all rule:
                {'service': 'http_status:404'},
            ],
        },
        opts=cloudflare_opts,
    )

    # create DNS records for ingresses, see             #
    # https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/routing-to-tunnel/dns/#create-a-dns-record-for-the-tunnel:
    zone = cloudflare.get_zone_output(
        filter={'match': 'all', 'name': component_config.cloudflare.zone},
        opts=p.InvokeOptions(provider=cloudflare_provider),
    )

    for ingress in component_config.cloudflared.ingress:
        cloudflare.DnsRecord(
            ingress.hostname,
            proxied=True,
            name=ingress.hostname.split('.')[0],
            type='CNAME',
            content=p.Output.format('{}.cfargotunnel.com', tunnel.id),
            ttl=1,
            zone_id=zone.zone_id,
            opts=cloudflare_opts,
        )
