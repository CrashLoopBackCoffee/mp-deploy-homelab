import pulumi as p
import pulumi_cloudflare as cloudflare
import pulumi_kubernetes as k8s

from ingress.cloudflared import create_cloudflared
from ingress.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().get_object('config'))

cloudflare_provider = cloudflare.Provider(
    'cloudflare',
    api_token=component_config.cloudflare.api_token.value,
)

k8s_stack = p.StackReference(f'{p.get_organization()}/kubernetes/{p.get_stack()}')
kube_config = k8s_stack.get_output('kube-config')
k8s_provider = k8s.Provider('k8s', kubeconfig=kube_config)

create_cloudflared(component_config, k8s_provider, cloudflare_provider)
