"""Configuration model."""

import ipaddress

import pydantic

from utils.model import CloudflareConfig, ConfigBaseModel, EnvVarRef


class ProxmoxConfig(ConfigBaseModel):
    node_name: str
    api_endpoint: pydantic.HttpUrl
    api_token: EnvVarRef
    verify_ssl: bool = True


class CertManagerConfig(ConfigBaseModel):
    version: str
    acme_email: pydantic.EmailStr


class TraefikConfig(ConfigBaseModel):
    version: str


class CsiDriverSmbConfig(ConfigBaseModel):
    version: str


class MetalLbConfig(ConfigBaseModel):
    version: str
    ipv4_start: ipaddress.IPv4Address
    ipv4_end: ipaddress.IPv4Address


class VirtualMachineConfig(ConfigBaseModel):
    name: str
    vmid: pydantic.PositiveInt
    ipv4_address: ipaddress.IPv4Interface
    cores: pydantic.PositiveInt
    memory_mb_min: pydantic.PositiveInt
    memory_mb_max: pydantic.PositiveInt
    root_disk_size_gb: pydantic.PositiveInt
    data_disk_size_gb: pydantic.PositiveInt


class MicroK8sConfig(ConfigBaseModel):
    cloud_image_url: pydantic.HttpUrl = pydantic.Field(
        default=pydantic.HttpUrl(
            'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img'
        )
    )
    ssh_user: str = 'ubuntu'
    ssh_public_key: str
    vlan_id: pydantic.PositiveInt | None = None
    master_nodes: list[VirtualMachineConfig]
    data_disk_mount: str = '/mnt/data'
    sub_domain: str | None = None


class UnifyConfig(ConfigBaseModel):
    url: pydantic.HttpUrl = pydantic.HttpUrl('https://unifi/')
    verify_ssl: bool = False
    internal_domain: str = 'erx.box'


class KubeStateMetricsConfig(ConfigBaseModel):
    version: str


class ComponentConfig(ConfigBaseModel):
    proxmox: ProxmoxConfig
    microk8s: MicroK8sConfig
    cloudflare: CloudflareConfig
    metallb: MetalLbConfig
    cert_manager: CertManagerConfig
    traefik: TraefikConfig
    unify: UnifyConfig = pydantic.Field(default_factory=UnifyConfig)
    csi_driver_smb: CsiDriverSmbConfig
    kube_state_metrics: KubeStateMetricsConfig
