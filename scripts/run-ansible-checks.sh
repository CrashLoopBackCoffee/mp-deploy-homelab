#!/usr/bin/env bash

set -x
set -eu

uv run ansible-galaxy collection install -r services/proxmox/ansible/ansible-requirements.yaml
uv run --directory services/proxmox/ansible ansible-lint -v inventory playbooks roles
