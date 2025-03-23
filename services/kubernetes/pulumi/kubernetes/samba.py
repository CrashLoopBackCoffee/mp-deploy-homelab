import pulumi as p
import pulumi_kubernetes as k8s

from kubernetes.model import ComponentConfig


def ensure_smb(component_config: ComponentConfig, k8s_provider: k8s.Provider):
    ns = k8s.core.v1.Namespace(
        'csi-driver-smb',
        metadata={
            'name': 'csi-driver-smb',
        },
        opts=p.ResourceOptions(provider=k8s_provider),
    )

    namespaced_k8s_provider = k8s.Provider(
        'csi-driver-smb',
        kubeconfig=k8s_provider.kubeconfig,  # pyright: ignore[reportAttributeAccessIssue]
        namespace=ns.metadata.name,
    )
    k8s_opts = p.ResourceOptions(provider=namespaced_k8s_provider)

    k8s.helm.v3.Release(
        'csi-driver-smb',
        chart='csi-driver-smb',
        version=component_config.csi_driver_smb.version,
        repository_opts={
            'repo': 'https://raw.githubusercontent.com/kubernetes-csi/csi-driver-smb/master/charts'
        },
        values={
            # https://github.com/kubernetes-csi/csi-driver-smb/tree/master/charts#tips
            'linux': {'kubelet': '/var/snap/microk8s/common/var/lib/kubelet'},
        },
        opts=k8s_opts,
    )

    samba_stack = p.StackReference(f'{p.get_organization()}/samba/{p.get_stack()}')
    samba_fqdn = samba_stack.get_output('fqdn')

    smb_secret = k8s.core.v1.Secret(
        'smb-secret',
        string_data={
            'username': samba_stack.get_output('smb-k8s-username'),
            'password': samba_stack.get_output('smb-k8s-password'),
        },
        opts=k8s_opts,
    )

    def create_storage_classes(shares):
        for share in shares:
            _create_smb_storage_class(
                f'samba-{share}',
                samba_fqdn=samba_fqdn,
                share=share,
                reclaim_policy='Delete',
                smb_secret=smb_secret,
                k8s_opts=k8s_opts,
            )

    samba_stack.get_output('smb-shares').apply(lambda names: create_storage_classes(names))


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
