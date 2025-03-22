#!/usr/bin/env bash

set -x
set -eu

uv run ruff format
uv run ruff check --fix
uv run pyright --warnings
uv run --directory services/proxmox/ansible ansible-lint -v inventory playbooks roles
