#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_CONTEXT="${ROOT_DIR}/src/debian-base1"
DOCKERFILE="${DOCKER_CONTEXT}/Dockerfile"
IMAGE_TAG="${IMAGE_TAG:-cis4900w26:latest}"

docker build -f "${DOCKERFILE}" -t "${IMAGE_TAG}" "${DOCKER_CONTEXT}"
