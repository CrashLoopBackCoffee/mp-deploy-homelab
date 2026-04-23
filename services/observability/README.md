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

- [ ] Status: Not started

- Define a top-level `ComponentConfig`.
- Add config sections for:
  - Grafana
  - Loki
  - Mimir
  - Alloy
  - ingress hostname
- Keep versions configurable in stack config and annotate them for Renovate.

### Phase 3: Namespace and Core Services

- [ ] Status: Not started

- Reference the `kubernetes` stack to obtain `kube-config`.
- Create the `observability` namespace.
- Deploy Loki and Mimir first so Grafana and Alloy have stable backends.
- Keep storage ephemeral in this phase.

### Phase 4: Grafana

- [ ] Status: Not started

- Deploy Grafana.
- Generate admin credentials and export them from the stack.
- Configure datasources for:
  - Loki
  - Mimir
- Expose Grafana with Traefik.
- Export the resulting FQDN from the stack.

### Phase 5: Alloy Gateway

- [ ] Status: Not started

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
