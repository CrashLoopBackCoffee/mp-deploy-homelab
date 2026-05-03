"""Observability stack entrypoint."""

import pulumi as p
import pulumi_kubernetes as k8s

from observability.app import create_observability
from observability.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().get_object('config') or {})

k8s_stack = p.StackReference(f'{p.get_organization()}/kubernetes/{p.get_stack()}')
kube_config = k8s_stack.get_output('kube-config')
k8s_provider = k8s.Provider('k8s', kubeconfig=kube_config)

create_observability(component_config, k8s_provider)
