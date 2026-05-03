"""Configuration model for the observability stack."""

import pydantic

from utils.model import ConfigBaseModel, get_pulumi_project


class GrafanaConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Grafana Helm chart version.')
    storage_class_name: str = pydantic.Field(
        default='data-hostpath-retained',
        description='Storage class for the Grafana data PVC.',
    )
    storage_size_gb: int = pydantic.Field(
        default=5,
        ge=1,
        description='Size of the Grafana data PVC in GiB.',
    )


class LokiConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Loki Helm chart version.')
    retention_days: int = pydantic.Field(
        default=30,
        ge=1,
        description='Loki log retention period in days.',
    )


class MimirConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Mimir Helm chart version.')
    retention_days: int = pydantic.Field(
        default=30,
        ge=1,
        description='Mimir metrics retention period in days.',
    )


class AlloyConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Alloy Helm chart version.')


class KubeStateMetricsConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='kube-state-metrics Helm chart version.')


class IngressConfig(ConfigBaseModel):
    hostname: str = pydantic.Field(description='Ingress hostname for Grafana.')


class ComponentConfig(ConfigBaseModel):
    grafana: GrafanaConfig = pydantic.Field(description='Grafana deployment configuration.')
    loki: LokiConfig = pydantic.Field(description='Loki deployment configuration.')
    mimir: MimirConfig = pydantic.Field(description='Mimir deployment configuration.')
    alloy: AlloyConfig = pydantic.Field(description='Alloy deployment configuration.')
    kube_state_metrics: KubeStateMetricsConfig = pydantic.Field(
        description='kube-state-metrics deployment configuration.'
    )
    ingress: IngressConfig = pydantic.Field(
        description='Ingress configuration for exposed endpoints.'
    )


class StackConfig(ConfigBaseModel):
    model_config = {
        'alias_generator': lambda field_name: f'{get_pulumi_project(__file__)}:{field_name}'
    }
    config: ComponentConfig


class PulumiConfigRoot(ConfigBaseModel):
    config: StackConfig
