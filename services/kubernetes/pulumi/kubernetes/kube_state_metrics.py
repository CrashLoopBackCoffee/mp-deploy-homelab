import pulumi as p
import pulumi_kubernetes as k8s

from kubernetes.model import ComponentConfig


def ensure_kube_state_metrics(component_config: ComponentConfig, k8s_provider: k8s.Provider):
    ns = k8s.core.v1.Namespace(
        'kube-state-metrics',
        metadata={
            'name': 'kube-state-metrics',
        },
        opts=p.ResourceOptions(provider=k8s_provider),
    )

    namespaced_k8s_provider = k8s.Provider(
        'kube-state-metrics-provider',
        kubeconfig=k8s_provider.kubeconfig,  # pyright: ignore[reportAttributeAccessIssue]
        namespace=ns.metadata['name'],
    )
    k8s_opts = p.ResourceOptions(provider=namespaced_k8s_provider)

    kube_state_metrics = k8s.helm.v3.Release(
        'kube-state-metrics',
        chart='kube-state-metrics',
        version=component_config.kube_state_metrics.version,
        repository_opts={'repo': 'https://prometheus-community.github.io/helm-charts'},
        values={
            'crds': {'enabled': True},
        },
        opts=k8s_opts,
    )

    service = kube_state_metrics.status.apply(
        lambda s: k8s.core.v1.Service.get(
            'kube-state-metrics',
            f'{s.namespace}/{s.name}',
            opts=k8s_opts,
        )
    )

    fqdn = f'kube-state-metrics.{component_config.microk8s.sub_domain}'

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
