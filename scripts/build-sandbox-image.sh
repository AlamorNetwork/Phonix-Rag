#!/usr/bin/env bash
# Build the sandbox image into the ROOTLESS daemon's image store.
#
# It has to be that daemon: it keeps its own images, and the rootful one's are invisible to it.
# Building here rather than pulling at run time also means a sandboxed command never needs
# network access to start.
set -euo pipefail

SANDBOX_USER="${SANDBOX_USER_NAME:-forge-sandbox}"
SANDBOX_UID="$(id -u "$SANDBOX_USER")"
IMAGE="${SANDBOX_IMAGE:-phoenix-forge-sandbox:latest}"
CONTEXT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker"

echo "Building $IMAGE into the rootless daemon of $SANDBOX_USER (uid $SANDBOX_UID)..."

install -d -o "$SANDBOX_USER" -g "$SANDBOX_USER" /tmp/forge-sandbox-build
install -m 0644 -o "$SANDBOX_USER" -g "$SANDBOX_USER" "$CONTEXT/sandbox.Dockerfile" /tmp/forge-sandbox-build/Dockerfile

sudo -u "$SANDBOX_USER" \
  XDG_RUNTIME_DIR="/run/user/$SANDBOX_UID" \
  DOCKER_HOST="unix:///run/user/$SANDBOX_UID/docker.sock" \
  docker build -t "$IMAGE" /tmp/forge-sandbox-build

rm -rf /tmp/forge-sandbox-build
echo "Done. The sandbox will start from $IMAGE with no network access."
