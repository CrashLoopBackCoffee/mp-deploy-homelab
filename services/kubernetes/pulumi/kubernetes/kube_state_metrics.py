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

    k8s.helm.v3.Release(
        'kube-state-metrics',
        chart='kube-state-metrics',
        version=component_config.kube_state_metrics.version,
        repository_opts={'repo': 'https://prometheus-community.github.io/helm-charts'},
        values={
            'crds': {'enabled': True},
        },
        opts=k8s_opts,
    )
