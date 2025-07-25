"""Confoguration of Microk8s on Proxmox VE."""

import os
import pathlib

import jinja2
import pulumi as p
import pulumi_command as command
import pulumi_kubernetes as k8s
import pulumi_proxmoxve as proxmoxve

from utils import unify

from kubernetes.cert_manager import ensure_cert_manager
from kubernetes.kube_state_metrics import ensure_kube_state_metrics
from kubernetes.metallb import ensure_metallb
from kubernetes.model import ComponentConfig
from kubernetes.samba import ensure_smb
from kubernetes.traefik import ensure_traefik


def create_microk8s(component_config: ComponentConfig, proxmox_provider: proxmoxve.Provider):
    proxmox_opts = p.ResourceOptions(provider=proxmox_provider)

    cloud_image = proxmoxve.download.File(
        'cloud-image',
        content_type='iso',
        datastore_id='local',
        node_name=component_config.proxmox.node_name,
        overwrite=False,
        overwrite_unmanaged=True,
        url=str(component_config.microk8s.cloud_image_url),
        opts=p.ResourceOptions.merge(
            proxmox_opts,
            p.ResourceOptions(retain_on_delete=True),
        ),
    )

    cloud_config_template = jinja2.Template(
        pathlib.Path('assets/cloud-init/cloud-config.yaml').read_text(),
        undefined=jinja2.StrictUndefined,
    )

    stack_name = p.get_stack()

    first_master_ipv4 = None
    for master_config in component_config.microk8s.master_nodes:
        cloud_config = proxmoxve.storage.File(
            f'cloud-config-master-{master_config.name}',
            node_name=component_config.proxmox.node_name,
            datastore_id='local',
            content_type='snippets',
            source_raw={
                'data': cloud_config_template.render(
                    master_config.model_dump()
                    | {
                        'username': component_config.microk8s.ssh_user,
                        'ssh_public_key': component_config.microk8s.ssh_public_key,
                        'data_disk_mount': component_config.microk8s.data_disk_mount,
                    }
                ),
                'file_name': f'cloud-config-{master_config.name}.yaml',
            },
            opts=p.ResourceOptions.merge(
                proxmox_opts,
                p.ResourceOptions(delete_before_replace=True),
            ),
        )

        gateway_address = str(master_config.ipv4_address.network.network_address + 1)

        vlan_config: proxmoxve.vm.VirtualMachineNetworkDeviceArgsDict = (
            {'vlan_id': int(component_config.microk8s.vlan_id)}
            if component_config.microk8s.vlan_id
            else {}
        )

        master_vm = proxmoxve.vm.VirtualMachine(
            master_config.name,
            name=master_config.name,
            node_name=component_config.proxmox.node_name,
            vm_id=master_config.vmid,
            tags=[stack_name],
            description='Kubernetes Master, maintained with Pulumi.',
            cpu={
                'cores': master_config.cores,
                # use exact CPU flags of host, as migration of VM for k8s nodes is irrelevant:
                'type': 'host',
            },
            memory={
                'dedicated': master_config.memory_mb_max,
                'floating': master_config.memory_mb_min,
            },
            cdrom={'file_id': None},  # pyright: ignore[reportArgumentType]
            disks=[
                {
                    'interface': 'virtio0',
                    'size': master_config.root_disk_size_gb,
                    'file_id': cloud_image.id,
                    'iothread': True,
                    'discard': 'on',
                    'file_format': 'raw',
                    # hack to avoid diff in subsequent runs:
                    'speed': {
                        'read': 10000,
                    },
                },
                {
                    'interface': 'virtio1',
                    'size': master_config.data_disk_size_gb,
                    'iothread': True,
                    'discard': 'on',
                    'file_format': 'raw',
                    # hack to avoid diff in subsequent runs:
                    'speed': {
                        'read': 10000,
                    },
                },
            ],
            network_devices=[
                {
                    'bridge': 'vmbr0',
                    'model': 'virtio',
                    **vlan_config,
                }
            ],
            agent={'enabled': True},
            initialization={
                # TODO Turn into state IP address and setup DNS when config is refactored.
                'ip_configs': [
                    {
                        'ipv4': {
                            'address': str(master_config.ipv4_address),
                            'gateway': gateway_address,
                        }
                    }
                ],
                'dns': {
                    'domain': 'local',
                    'servers': [gateway_address],
                },
                'user_data_file_id': cloud_config.id,
            },
            stop_on_destroy=True,
            on_boot=stack_name == 'prod',
            machine='q35',
            # Linux 2.6+:
            operating_system={'type': 'l26'},
            opts=p.ResourceOptions.merge(
                proxmox_opts,
                p.ResourceOptions(ignore_changes=['cdrom']),
            ),
        )

        master_vm_ipv4 = master_vm.ipv4_addresses[1][0]
        p.export(f'{master_config.name}-ipv4', master_vm_ipv4)

        # create DNS entries for master nodes:
        dns_provider = unify.UnifyDnsRecordProvider(
            base_url=str(component_config.unify.url),
            api_token=os.environ['UNIFY_API_TOKEN__PULUMI'],
            verify_ssl=component_config.unify.verify_ssl,
        )

        unify.UnifyDnsRecord(
            f'{master_config.name}-dns',
            domain_name=f'{master_config.name}.{component_config.unify.internal_domain}',
            ipv4=master_vm_ipv4,
            provider=dns_provider,
        )

        if not first_master_ipv4:
            first_master_ipv4 = master_vm_ipv4

    # configure cluster level properties:
    if first_master_ipv4:
        master_connection = command.remote.ConnectionArgs(
            host=first_master_ipv4,
            user=component_config.microk8s.ssh_user,
        )

        kube_config_command = command.remote.Command(
            'kube-config',
            connection=master_connection,
            add_previous_output_in_env=False,
            create='microk8s config',
            # only log stderr and mark stdout as secret as it contains the private keys to cluster:
            logging=command.remote.Logging.STDERR,
            opts=p.ResourceOptions(additional_secret_outputs=['stdout']),
        )

        kube_config = kube_config_command.stdout

        # export to kube config with
        # p stack output --show-secrets kube-config > ~/.kube/config
        p.export('kube-config', kube_config)

        k8s_provider = k8s.Provider(
            'microk8s',
            kubeconfig=kube_config,
            enable_server_side_apply=True,
        )

        k8s_opts = p.ResourceOptions(provider=k8s_provider)

        # create hostpath storage class to use mounted data disk:
        k8s.storage.v1.StorageClass(
            'data-hostpath',
            metadata={
                'name': 'data-hostpath',
                'annotations': {
                    'storageclass.kubernetes.io/is-default-class': 'true',
                },
            },
            provisioner='microk8s.io/hostpath',
            parameters={'pvDir': component_config.microk8s.data_disk_mount},
            reclaim_policy='Delete',
            volume_binding_mode='WaitForFirstConsumer',
            opts=k8s_opts,
        )

        # create second hostpath storage class for precious data:
        k8s.storage.v1.StorageClass(
            'data-hostpath-retained',
            metadata={
                'name': 'data-hostpath-retained',
            },
            provisioner='microk8s.io/hostpath',
            parameters={'pvDir': component_config.microk8s.data_disk_mount},
            reclaim_policy='Retain',
            volume_binding_mode='WaitForFirstConsumer',
            opts=k8s_opts,
        )

        # remove the default annotation from the hostpath storage class (just setting the pvDir
        # parameter is not possible as patches do not allow for parameter updates):
        k8s.storage.v1.StorageClassPatch(
            'hostpath-old-default-removal',
            metadata={
                # name as given by microk8s:
                'name': 'microk8s-hostpath',
                'annotations': {
                    'storageclass.kubernetes.io/is-default-class': 'false',
                    'pulumi.com/patchForce': 'true',
                },
            },
            opts=k8s_opts,
        )

        metallb = ensure_metallb(component_config, k8s_provider)
        cert_manager = ensure_cert_manager(component_config, k8s_provider)
        ensure_traefik(
            component_config,
            metallb=metallb,
            cert_manager=cert_manager,
            k8s_provider=k8s_provider,
        )

        ensure_smb(component_config, k8s_provider)
        ensure_kube_state_metrics(component_config, k8s_provider)
