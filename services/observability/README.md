# Observability Plan

## Goal

Create a dedicated `observability` Pulumi stack that deploys a namespace-scoped
observability platform to the MicroK8s cluster.

Initial scope:

- Grafana
- Mimir
- Loki
- Alloy as a central OpenTelemetry gateway

Future scope:

- Tempo in the same stack

## Guiding Decisions

- Deploy everything into the dedicated Kubernetes namespace `observability`.
- Use monolithic or single-binary deployment modes first to reduce operational
  complexity. For the expected homelab scale, this should be a reasonable
  tradeoff and should not be a major performance problem.
- Start without PVCs so the stack can be created, tested, and torn down
  repeatedly without manual storage cleanup.
- Add persistence later, once the basic stack shape is working reliably.
- When persistence is introduced, prefer the preexisting retained storage class
  by default and keep the storage class configurable.
- Follow the existing project pattern:
  - one Pulumi service under `services/observability`
  - config validated with Pydantic
  - stack references to the `kubernetes` stack

## Proposed Architecture

### Namespace

- Create the namespace `observability`.
- Keep shared secrets, config maps, services, and ingress resources inside this
  namespace.

### Storage

- Initial rollout is intentionally ephemeral and should avoid PVCs.
- Loki, Mimir, and Grafana should be wired so persistence can be introduced
  later with minimal structural change.
- Once persistence is added:
  - start with one PVC per stateful component
  - default to the existing retained storage class
  - treat size changes as an explicit migration concern, not as something to
    rely on casually during early rollout

### Workloads

- Grafana:
  - single deployment
  - generated admin credentials
  - preconfigured datasources for Loki and Mimir
- Loki:
  - monolithic deployment
  - filesystem-based local storage layout
  - service exposed only inside the cluster
- Mimir:
  - monolithic deployment
  - filesystem-backed local storage layout
  - service exposed only inside the cluster
- Alloy:
  - central gateway deployment
  - receives OTLP data from applications
  - forwards metrics to Mimir and logs to Loki
  - also acts as the first place to collect cluster metrics and logs so we do
    not need a separate observability ingestion layer right now
  - keep traces routing in mind so Tempo can be added later without redesigning
    exporters

### Networking

- Expose Grafana through Traefik in the cluster.
- Prefer an internal wildcard hostname first, following the existing
  `app.<domain>` pattern used by other services.
- Keep Loki, Mimir, and Alloy cluster-internal unless a concrete external use
  case appears.

## Current Decisions

- Namespace name: `observability`
- Initial stack scope: one `observability` stack with `prod` config only
- Deployment mode: monolithic where available
- Grafana admin credentials: generated
- Persistence: deferred until after the first working stack
- Default persistence direction later: existing retained storage class
- Cluster metrics and logs: collected by the same Alloy deployment
- Tempo later: added to the same stack

## Cluster Ingestion Opportunities

The current stack already has Grafana, Mimir, Loki, and Alloy running in the
`observability` namespace. Alloy currently acts as an OTLP gateway and forwards
Kubernetes events to Loki. The cluster also exposes several metric and log
sources that can be added incrementally.

### Current Ingestion State

| Area | Available now | Currently ingested | Notes |
| --- | --- | --- | --- |
| OTLP application metrics and logs | Yes | Yes, when applications send OTLP | Alloy exposes OTLP gRPC on `4317` and OTLP HTTP on `4318`; metrics go to Mimir and logs go to Loki. |
| Kubernetes events | Yes | Yes | Alloy already uses `loki.source.kubernetes_events`. |
| Pod and container logs | Yes | Yes | Alloy discovers pods with `discovery.kubernetes`, relabels namespace, pod, container, node, and app labels, tails logs with `loki.source.kubernetes`, and drops backlog entries older than Loki accepts. |
| Node and pod CPU/memory live metrics | Yes | Not intended | `metrics-server` is installed and `kubectl top nodes/pods` works, but it is not intended as the observability ingestion source; use kubelet/cAdvisor scraping instead. |
| Kubelet and cAdvisor metrics | Yes | No | The kubelet cAdvisor endpoint is reachable through the API server node proxy. |
| Kubernetes API server metrics | Yes | No | The API server `/metrics` endpoint is reachable. |
| Service and pod Prometheus metrics | Yes | No | Several services expose metrics ports; cert-manager, CoreDNS, and Traefik already advertise scrape metadata. |
| Kubernetes object state metrics | Partly | No | `kube-state-metrics` has been removed, so classic `kube_*` object state series are not currently available. |

### Candidate Sources

| Source | What it would provide | Ready now | Required changes |
| --- | --- | --- | --- |
| Kubernetes pod logs | stdout/stderr logs for application and platform pods | Yes | Enabled through Alloy Kubernetes pod discovery, `loki.source.kubernetes`, and relabeling for namespace, pod, container, node, and app labels. |
| Kubernetes events | Scheduling, image pull, restart, and volume events | Yes | Already enabled; optionally improve labels and retention expectations. |
| Kubelet `/metrics/cadvisor` | Container CPU, memory, filesystem, network, and per-pod usage history | Yes | Add Alloy node discovery and `prometheus.scrape` through the API server node proxy or kubelet HTTPS endpoint; apply metric filtering to control cardinality. |
| Kubelet `/metrics` and `/metrics/resource` | Kubelet health, runtime, and pod resource metrics | Yes | Add the same node-based scrape path used for cAdvisor. |
| Kubernetes API server `/metrics` | API request rate, latency, errors, watches, and API health | Yes | Add an authenticated scrape of the Kubernetes service/API endpoint using the Alloy service account token and cluster CA. |
| CoreDNS | DNS request volume, latency, cache behavior, and errors | Yes | Add service discovery scraping for the `kube-dns` metrics port `9153`. |
| cert-manager | Certificate, ACME order, challenge, and controller metrics | Yes | Add annotation-based pod scraping; cert-manager pods advertise scrape metadata on port `9402`. |
| Traefik | Ingress request count, latency, routers, services, and entrypoint metrics | Yes | Add annotation-based pod scraping; the Traefik pod advertises scrape metadata on port `9100`. |
| Mimir, Loki, Grafana, and Alloy self-metrics | Health and performance of the observability stack | Yes | Add explicit scrapes for observability services with metrics ports. |
| Loki cache metrics | Memcached cache hit/miss, eviction, and memory metrics | Yes | Scrape the Loki cache exporter ports exposed as `http-metrics` on `9150`. |
| MetalLB metrics | Controller, speaker, and advertisement metrics | Likely | Add or verify MetalLB metrics service exposure and scrape the controller/speaker metrics endpoints. |
| Kubernetes object state | Deployment replica state, pod phase, PVC status, job state, and restart metadata | Partly | Prefer adding Alloy's Kubernetes cluster receiver if it covers the needed dashboards; otherwise redeploy `kube-state-metrics` in `observability`. |
| Node OS metrics | Disk, filesystem, load, systemd, and host network metrics | No | Add node-exporter, or run Alloy as a DaemonSet with host mounts and a node/unix exporter component. |
| Node system logs | MicroK8s, kubelet, container runtime, and systemd logs | No | Add DaemonSet-style log collection with host mounts for journald and MicroK8s log paths. |

### Suggested Order

| Priority | Add | Reason |
| --- | --- | --- |
| 1 | Pod logs with `loki.source.kubernetes` | Completed; Alloy now tails Kubernetes pod and container logs into Loki. |
| 2 | Kubelet and cAdvisor metrics | Provides durable pod, container, and node resource history in Mimir. |
| 3 | Annotation and service-port Prometheus scraping | Quickly captures cert-manager, CoreDNS, Traefik, and observability-stack self-metrics. |
| 4 | Kubernetes object state metrics | Restores deployment, pod phase, PVC, job, and restart-state visibility without necessarily bringing back a separate kube-state-metrics deployment. |
| 5 | Node OS logs and metrics | Useful for host-level troubleshooting, but it requires DaemonSet-style deployment or an additional exporter. |

The cluster does not currently have the Prometheus Operator
`monitoring.coreos.com` ServiceMonitor/PodMonitor CRDs installed. Native Alloy
discovery and scrape configuration therefore fits the current cluster better
than introducing ServiceMonitor-based collection right now.

## Delivery Plan

### Phase 1: Stack Skeleton

- [x] Status: Completed

- Create the Python package and Pulumi project structure.
- Add:
  - `pyproject.toml`
  - `pulumi/Pulumi.yaml`
  - `pulumi/Pulumi.prod.yaml`
  - `pulumi/__main__.py`
  - `pulumi/observability/model.py`
  - `pulumi/observability/*.py` component modules
- Register the package in the root workspace like the other services.

### Phase 2: Shared Config Model

- [x] Status: Completed

- Define a top-level `ComponentConfig`.
- Add config sections for:
  - Grafana
  - Loki
  - Mimir
  - Alloy
  - ingress hostname
- Keep versions configurable in stack config and annotate them for Renovate.

### Phase 3: Namespace and Core Services

- [x] Status: Completed

- Reference the `kubernetes` stack to obtain `kube-config`.
- Create the `observability` namespace.
- Deploy Loki and Mimir first so Grafana and Alloy have stable backends.
- Keep storage ephemeral in this phase.

### Phase 4: Grafana

- [x] Status: Completed

- Deploy Grafana.
- Generate admin credentials and export them from the stack.
- Configure datasources for:
  - Loki
  - Mimir
- Expose Grafana with Traefik.
- Export the resulting FQDN from the stack.

### Phase 5: Alloy Gateway

- [x] Status: Completed

- Deploy Alloy as the central OTLP endpoint.
- Configure pipelines for:
  - OTLP metrics -> Mimir
  - OTLP logs -> Loki
- Add the first cluster-level collection pipelines here as well, as long as the
  operational model stays simple.
- Leave a clean extension point for:
  - OTLP traces -> Tempo
- Export the in-cluster endpoint details so application stacks can reference
  them later.

### Phase 6: Persistence

- [ ] Status: Not started

- Introduce PVC-backed storage only after the ephemeral stack works well.
- Default to the existing retained storage class, but keep it configurable.
- Add protection for critical PVC-backed resources in `prod` where appropriate.
- Document any resize or migration procedure explicitly before relying on it.

### Phase 7: Hardening and Reuse

- [ ] Status: Not started

- Add health probes and conservative resource requests.
- Consider extracting common helpers if the service repeats namespace or ingress
  patterns already used elsewhere.
