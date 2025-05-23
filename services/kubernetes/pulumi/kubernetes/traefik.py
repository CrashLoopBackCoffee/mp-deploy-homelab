"""Installation of traefik ingress controller."""

import os

import pulumi as p
import pulumi_kubernetes as k8s

from utils import unify

from kubernetes.model import ComponentConfig


def ensure_traefik(
    component_config: ComponentConfig,
    *,
    metallb: p.Resource,
    cert_manager: p.Resource,
    k8s_provider: k8s.Provider,
):
    ns = k8s.core.v1.Namespace(
        'traefik',
        metadata={
            'name': 'traefik',
        },
        opts=p.ResourceOptions(provider=k8s_provider),
    )

    namespaced_k8s_provider = k8s.Provider(
        'traefik-provider',
        kubeconfig=k8s_provider.kubeconfig,  # pyright: ignore[reportAttributeAccessIssue]
        namespace=ns.metadata['name'],
    )
    k8s_opts = p.ResourceOptions(provider=namespaced_k8s_provider)

    traefik = k8s.helm.v3.Release(
        'traefik',
        chart='traefik',
        version=component_config.traefik.version,
        repository_opts={'repo': 'https://traefik.github.io/charts'},
        values={
            'additionalArguments': [
                # expose the API directly from the pod to allow getting access to dashboard at
                # http://localhost:8080/ after kubectl port-forwarding:
                '--api.insecure=true',
            ]
        },
        # depend on metallb to ensure the service gets a public IP queried below:
        opts=p.ResourceOptions.merge(k8s_opts, p.ResourceOptions(depends_on=[metallb])),
    )

    service = traefik.status.apply(
        lambda s: k8s.core.v1.Service.get(
            'traefik',
            f'{s.namespace}/{s.name}',
            opts=k8s_opts,
        )
    )

    ipv4 = service.status.load_balancer.ingress[0].ip
    p.export('app-ipv4', ipv4)

    p.export('app-sub-domain', component_config.microk8s.sub_domain)
    if component_config.microk8s.sub_domain:
        wildcard_domain = f'*.{component_config.microk8s.sub_domain}'

        # create wildcard certificate:
        certificate = k8s.apiextensions.CustomResource(
            'certificate',
            api_version='cert-manager.io/v1',
            kind='Certificate',
            metadata={
                'name': 'certificate',
                'annotations': {
                    # wait for certificate to be issued before starting deployment (and hence application
                    # containers):
                    'pulumi.com/waitFor': 'condition=Ready',
                },
            },
            spec={
                'secretName': 'certificate',
                'dnsNames': [wildcard_domain],
                'issuerRef': {
                    'kind': 'ClusterIssuer',
                    'name': 'lets-encrypt',
                },
            },
            opts=p.ResourceOptions.merge(k8s_opts, p.ResourceOptions(depends_on=[cert_manager])),
        )

        # use this certificate as traefik's new default:
        k8s.apiextensions.CustomResource(
            'default',
            api_version='traefik.io/v1alpha1',
            kind='TLSStore',
            metadata={'name': 'default'},
            spec={
                'defaultCertificate': {
                    'secretName': certificate.metadata['name'],  # pyright: ignore[reportAttributeAccessIssue]
                }
            },
            opts=k8s_opts,
        )

        # create wildcard DNS record:
        dns_provider = unify.UnifyDnsRecordProvider(
            base_url=str(component_config.unify.url),
            api_token=os.environ['UNIFY_API_TOKEN__PULUMI'],
            verify_ssl=component_config.unify.verify_ssl,
        )

        unify.UnifyDnsRecord(
            'traefik-dns',
            domain_name=wildcard_domain,
            ipv4=ipv4,
            provider=dns_provider,
        )
