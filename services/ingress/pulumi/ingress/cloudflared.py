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
    # k8s_opts = p.ResourceOptions(provider=k8s_provider)
    cloudflare_opts = p.ResourceOptions(provider=cloudflare_provider)
    cloudflare_invoke_opts = p.InvokeOptions(provider=cloudflare_provider)

    # Create a Cloudflared tunnel
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

    tunnel_token = cloudflare.get_zero_trust_tunnel_cloudflared_token_output(
        account_id=cloudflare_account_id, tunnel_id=tunnel.id, opts=cloudflare_invoke_opts
    )
