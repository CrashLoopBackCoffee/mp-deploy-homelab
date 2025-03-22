#!/usr/bin/env bash

set -x
set -eu

uv run ruff format
uv run ruff check --fix
uv run pyright --warnings
# uv run ansible-lint \
#           services/proxmox/ansible/inventory \
#           services/proxmox/ansible/playbooks \
#           services/proxmox/ansible/roles
