"""Configuration model for the observability stack."""

import pydantic

from utils.model import ConfigBaseModel, PulumiSecret, get_pulumi_project


class GrafanaConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Grafana Helm chart version.')
    admin_password: PulumiSecret | None = pydantic.Field(
        default=None,
        description='Grafana admin password. Generated when unset.',
    )
    storage_class_name: str = pydantic.Field(
        default='data-hostpath-retained',
        description='Storage class for the Grafana data PVC.',
    )
    storage_size_gb: int = pydantic.Field(
        default=5,
        ge=1,
        description='Size of the Grafana data PVC in GiB.',
    )
    backup_enabled: bool = pydantic.Field(
        default=True,
        description='Whether to create the Grafana backup CronJob.',
    )
    backup_schedule: str = pydantic.Field(
        default='0 */2 * * *',
        description='Cron schedule for the Grafana backup job.',
    )
    backup_storage_class_name: str = pydantic.Field(
        default='samba-write-k8s',
        description='Storage class for the Grafana backup PVC.',
    )
    backup_storage_size_gb: int = pydantic.Field(
        default=5,
        ge=1,
        description='Size of the Grafana backup PVC in GiB.',
    )
    backup_python_version: str = pydantic.Field(
        description='Python image tag used by the Grafana backup CronJob.',
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


class StaticScrapeTarget(ConfigBaseModel):
    name: str = pydantic.Field(description='Alloy component name for this scrape target.')
    job_name: str = pydantic.Field(description='Prometheus job label for scraped samples.')
    address: str = pydantic.Field(description='Host and port scraped by Alloy.')
    metrics_path: str = pydantic.Field(
        default='/metrics',
        description='HTTP path that exposes Prometheus metrics.',
    )
    scrape_interval: str = pydantic.Field(
        default='30s',
        description='How often Alloy scrapes this target.',
    )
    scrape_timeout: str = pydantic.Field(
        default='10s',
        description='How long Alloy waits for a scrape response.',
    )
    labels: dict[str, str] = pydantic.Field(
        default_factory=dict,
        description='Additional static labels to attach to the target.',
    )


class AlloyConfig(ConfigBaseModel):
    version: str = pydantic.Field(description='Alloy Helm chart version.')
    static_scrape_targets: list[StaticScrapeTarget] = pydantic.Field(
        default_factory=list,
        description='Explicit non-Kubernetes Prometheus scrape targets.',
    )


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
