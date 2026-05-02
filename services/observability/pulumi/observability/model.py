"""Configuration model for the observability stack."""

import pydantic

from utils.model import ConfigBaseModel, get_pulumi_project


class GrafanaConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Grafana Helm chart version.')


class LokiConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Loki Helm chart version.')


class MimirConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Mimir Helm chart version.')


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
