#!/usr/bin/env bash

set -x
set -eu

./scripts/run-ansible-checks.sh
./scripts/run-python-checks.sh
