# Observability Stack

This service deploys the homelab observability platform into the MicroK8s
cluster. It is managed by the Pulumi project in `services/observability/pulumi`
and runs in the `observability` namespace.

The stack is intentionally single-node oriented. It favors simple, retained
local storage over high availability because the current cluster is a
single-node homelab cluster.

## Components

| Component | Purpose | Notes |
| --- | --- | --- |
| Grafana | Dashboards and UI | Exposed through Traefik. Uses PVC-backed SQLite state and a backup CronJob. |
| Loki | Logs | Single-binary mode with filesystem storage on a retained PVC. |
| Mimir | Metrics | Distributed chart in a single-node posture. Uses bundled MinIO as the object-store API. |
| MinIO | Mimir object storage | Bundled by the Mimir chart, standalone mode, retained PVC. |
| Alloy | Ingestion gateway and collector | Receives OTLP, tails Kubernetes logs, scrapes metrics, and forwards to Loki/Mimir. |
| kube-state-metrics | Kubernetes object metrics | Scraped by Alloy into Mimir. |

Tempo is not deployed yet. Alloy is already the natural place to add OTLP trace
routing later.

## Data Flow

Alloy is the central ingestion boundary:

- OTLP gRPC on `alloy.observability.svc.cluster.local:4317`
- OTLP HTTP on `http://alloy.observability.svc.cluster.local:4318`
- Loki-compatible push API on
  `http://alloy.observability.svc.cluster.local:3100`

Alloy forwards:

- OTLP metrics to Mimir remote write.
- OTLP logs to Loki.
- Kubernetes pod logs to Loki.
- Kubernetes events to Loki.
- Kubernetes API server, kubelet, kubelet resource, cAdvisor, and
  kube-state-metrics metrics to Mimir.
- Static scrape targets from prod config to Mimir.

Current static scrape targets are:

- `pbs.mpagel.de:9100` node-exporter
- `pve-02.mpagel.de:9100` node-exporter
- `pve-02.mpagel.de:9221/pve` Proxmox VE exporter
- `ha.mpagel.de/api/prometheus` Home Assistant metrics, with bearer-token auth

Check target health with:

```promql
up
up{source="proxmox"}
up{source="homeassistant"}
```

## Networking

Grafana is exposed through Traefik at:

```text
grafana.app.mpagel.de
```

External log producers can push Loki-format logs through Alloy at:

```text
https://logs.app.mpagel.de/loki/api/v1/push
```

That endpoint is protected with Traefik BasicAuth. The generated credentials
are exported from the Pulumi stack as:

- `logs-ingest-username`
- `logs-ingest-password`
- `logs-ingest-url`

Loki and Mimir remain cluster-internal. Stable in-cluster gateway Services are
created for consumers:

- `loki-gateway.observability.svc.cluster.local`
- `mimir.observability.svc.cluster.local`

Grafana uses those Services as its Loki and Mimir datasources.

## Persistence

Observability storage has two classes of data:

- Grafana state is small and important configuration data.
- Loki and Mimir data is bulky telemetry data that should survive pod restarts
  and node reboots, but is intentionally not backed up.

Current storage:

| Data | StorageClass | Size | Backup expectation |
| --- | --- | ---: | --- |
| Grafana live state | `data-hostpath-retained` | `5Gi` | Backed up by CronJob |
| Grafana backups | `samba-write-k8s` | `5Gi` | Backup destination |
| Loki data | `bulk-hostpath-retained` | `25Gi` | Not backed up |
| Mimir MinIO | `bulk-hostpath-retained` | `100Gi` | Not backed up |
| Mimir ingester | `bulk-hostpath-retained` | `20Gi` | Not backed up |
| Mimir store-gateway | `bulk-hostpath-retained` | `10Gi` | Not backed up |
| Mimir compactor | `bulk-hostpath-retained` | `10Gi` | Not backed up |
| Mimir alertmanager | `bulk-hostpath-retained` | `1Gi` | Not backed up |

`bulk-hostpath-retained` is created by the Kubernetes stack with the
`microk8s.io/hostpath` provisioner and points at `/mnt/bulk`, a UUID-mounted
USB disk attached to the Kubernetes VM. It uses `reclaimPolicy: Retain`.

Operational implications:

- Hostpath volumes are node-local. They fit the current single-node cluster,
  but they are not portable high-availability storage.
- The retained telemetry PVCs are intended to survive Helm release replacement,
  StatefulSet recreation, pod restarts, and node reboots.
- MicroK8s hostpath does not behave like a hard per-PVC filesystem quota. The
  requested PVC sizes are operational boundaries, while the physical USB disk
  is the real capacity limit.
- Shrinking PVCs is not supported. Treat size reductions as migration work.

## Retention

Prod configuration sets both log and metric retention to 15 days:

| System | Setting | Current prod value |
| --- | --- | --- |
| Loki | `limits_config.retention_period` | `15d` |
| Mimir | `limits.compactor_blocks_retention_period` | `15d` |

Retention is the primary data boundary. PVC sizes are safety and capacity
planning boundaries.

## Grafana Backup

Grafana uses a retained PVC for live SQLite state. A CronJob periodically backs
up:

- the Grafana SQLite database, using SQLite's backup API
- the Grafana secret key used to decrypt secure settings

The secret key must be restored with the database. Without it, restored secure
fields such as datasource credentials may not be usable.

The configured Grafana admin password is a stack-owned input, but Grafana may
store the admin password in its database after first boot. Changing the Pulumi
config does not necessarily reset an existing database user. Use an explicit
Grafana password reset path if that needs to be enforced.

## Deployment Notes

Useful commands:

```sh
direnv exec . pulumi preview --cwd services/observability/pulumi -s prod
direnv exec . pulumi up --cwd services/observability/pulumi -s prod
```

Configuration schema generation:

```sh
uv run python scripts/generate-config-schema.py
```

The Loki and Mimir persistence migrations required StatefulSet recreation
because Kubernetes does not allow changing `volumeClaimTemplates` in place. If
future changes alter StatefulSet PVC templates, expect the same operational
pattern:

1. Preview the change.
2. Let Pulumi/Helm attempt the update, or identify affected StatefulSets from
   the preview.
3. Orphan-delete the affected StatefulSets.
4. Delete their old pods.
5. Re-run `pulumi up`.
6. Confirm PVCs bind, pods are ready, and a final preview reports no drift.

Avoid casual PVC size changes on the stateful telemetry components. Growing
PVCs may still require component-specific operational care; shrinking requires
migration.

## Current Gaps

- Tempo is not deployed.
- Node OS metrics and systemd/journald logs from the Kubernetes VM are not
  collected yet.
- Annotation-based scraping for services such as CoreDNS, cert-manager,
  Traefik, and observability self-metrics is not generalized yet.
- Grafana restore steps are not documented in this repo.
- Disk/PVC usage alerting still needs to be added before treating the storage
  model as fully operated.
