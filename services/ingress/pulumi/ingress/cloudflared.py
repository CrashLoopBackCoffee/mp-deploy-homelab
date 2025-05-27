import pulumi_cloudflare as cloudflare
import pulumi_kubernetes as k8s

from ingress.model import ComponentConfig


def create_cloudflared(
    component_config: ComponentConfig,
    k8s_provider: k8s.Provider,
    cloudflare_provider: cloudflare.Provider,
):
    pass
