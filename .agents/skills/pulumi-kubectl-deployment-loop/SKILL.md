---
name: pulumi-kubectl-deployment-loop
description: Use when developing, deploying, or troubleshooting this repo's Pulumi-managed services and the task requires using Pulumi plus kubectl against the MicroK8s production cluster until workloads are healthy and the final Pulumi diff is zero.
argument-hint: service or stack name, for example: observability
---

# Pulumi Kubectl Deployment Loop

Use this skill for repo work that changes or verifies a Pulumi-managed deployment.

## Cluster and Commands

- Production kubeconfig: `/home/mike/.kube/microk8s-prod`.
- Run Pulumi from the service's `services/<service>/pulumi` directory.
- Prefer `direnv exec . pulumi ...` so the repo environment and schema generation hooks run.
- Use `kubectl --kubeconfig /home/mike/.kube/microk8s-prod ...` for cluster inspection.

## Feedback Loop

1. Inspect local state with `git status --short` and avoid overwriting unrelated user changes.
2. Read the relevant Pulumi code, stack YAML, generated templates, and current cluster state before editing.
3. Make the smallest repo change that should fix the deployment or behavior.
4. Run `direnv exec . pulumi preview --stack prod --diff` from the affected Pulumi project.
5. If the preview is unexpected, fix the repo change before applying.
6. Apply with `direnv exec . pulumi up --stack prod --yes --skip-preview` after a clean expected preview.
7. Verify with kubectl:
   - `rollout status` for Deployments or StatefulSets that should roll.
   - `get pods,svc,cm,secret,ingress` as relevant.
   - `logs`, `describe`, and `get events` for failures.
   - service-specific health checks or in-cluster queries when behavior matters.
8. If Pulumi or kubectl shows errors, iterate: inspect the failure, patch the repo, preview, apply, and verify again.
9. Finish only when the workload is healthy and `direnv exec . pulumi preview --stack prod --diff` shows no changes. If a zero diff is impossible or unsafe, report the exact residual diff and why.

## Reporting

- Summarize the changed files and the Pulumi update number when an update was applied.
- Include the most important kubectl evidence, such as rollout success, active pod readiness, and live ConfigMap or service details.
- Mention expected rollout noise separately from real residual errors.
